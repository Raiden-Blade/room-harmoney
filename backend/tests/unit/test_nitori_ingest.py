"""ニトリ実商品CSV → products.json 変換（`backend/ingest/nitori_ingest.py`）の単体テスト。
段階B1（実データ投入）ゲート。

重点観点（実装指示より）:
  (1) parse_price（単一/レンジ/カンマ/空）
  (2) extract_color（複合色優先・非一致時は空文字）
  (3) 大分類マップ（中分類→大分類）
  (4) dedup（商品コード重複はファイル名昇順で先勝ち）
  (5) assign_location が store_map の実在ノードの floor/x/y/zone を返す
  (6) 出力スキーマの完全性

9,180件の実データではなく、小さなインラインCSV/店舗データで検証する
（`data/store_map.json` は小さいファイルのため実データをそのまま使う）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.nitori_ingest import (
    MID_TO_LARGE,
    MID_TO_WAYPOINT_ID,
    SUB_PASSAGE_MIDS,
    assign_location,
    build_products,
    extract_color,
    parse_price,
    resolve_waypoint_location,
    run,
)

from tests.fixtures import DATA_DIR as FIXTURES_DATA_DIR


# ---------------------------------------------------------------------------
# (1) parse_price
# ---------------------------------------------------------------------------


def test_parse_price_single_value():
    assert parse_price("30990円") == 30990


def test_parse_price_range_takes_lower_bound():
    assert parse_price("37990～47990円") == 37990
    # 全角チルダ表記の別バリエーションにも対応。
    assert parse_price("37990〜47990円") == 37990


def test_parse_price_strips_commas():
    assert parse_price("1,234円") == 1234
    assert parse_price("12,345〜23,456円") == 12345


def test_parse_price_returns_zero_when_no_digits():
    assert parse_price("") == 0
    assert parse_price("価格未定") == 0
    assert parse_price(None) == 0


# ---------------------------------------------------------------------------
# (2) extract_color
# ---------------------------------------------------------------------------


def test_extract_color_matches_simple_color():
    assert extract_color("ソファ 布張りタイプ (ホワイト)") == "ホワイト"


def test_extract_color_prefers_compound_color_over_substring_color():
    """複合色（ライトグレー）はその部分文字列である単色（グレー）より優先されること。"""
    assert extract_color("ラグ ライトグレー 200x250") == "ライトグレー"
    assert extract_color("チェスト ダークブラウン 3段") == "ダークブラウン"
    assert extract_color("カーテン グレージュ 100x200") == "グレージュ"


def test_extract_color_returns_empty_when_no_match():
    assert extract_color("収納ボックス Lサイズ フタ付き") == ""
    assert extract_color("") == ""
    assert extract_color(None) == ""


# ---------------------------------------------------------------------------
# (3) 大分類マップ
# ---------------------------------------------------------------------------


def test_mid_to_large_map_covers_all_9_mid_categories():
    expected_mids = {
        "ソファ",
        "椅子・チェア",
        "テーブル",
        "テレビ台・リビング収納・仏壇",
        "収納家具",
        "カーペット・ラグ・マット",
        "カーテン",
        "クッション・カバー",
        "ライト・照明器具",
    }
    assert set(MID_TO_LARGE.keys()) == expected_mids


def test_mid_to_large_map_groups_correctly():
    furniture = {"ソファ", "椅子・チェア", "テーブル", "テレビ台・リビング収納・仏壇", "収納家具"}
    fabric = {"カーペット・ラグ・マット", "カーテン", "クッション・カバー"}
    lighting = {"ライト・照明器具"}

    for mid in furniture:
        assert MID_TO_LARGE[mid] == "家具"
    for mid in fabric:
        assert MID_TO_LARGE[mid] == "ファブリック"
    for mid in lighting:
        assert MID_TO_LARGE[mid] == "照明"


def test_sub_passage_mids_are_cushion_and_lighting_only():
    assert SUB_PASSAGE_MIDS == frozenset({"クッション・カバー", "ライト・照明器具"})


# ---------------------------------------------------------------------------
# (4) dedup（ファイル名昇順で先勝ち）
# ---------------------------------------------------------------------------


def _small_store_map() -> dict:
    """テスト用の小さな店舗マップ（1フロア・ゾーン1つ・サブ通路1つ）。実データではない。"""
    return {
        "floors": [
            {
                "floor": 1,
                "waypoints": [
                    {"id": "f1_zoneA", "floor": 1, "x": 20, "y": 20, "type": "ゾーン"},
                    {"id": "wp_near", "floor": 1, "x": 17, "y": 18, "type": "商品近傍"},
                    {"id": "sub_1", "floor": 1, "x": 95, "y": 88, "type": "サブ通路"},
                ],
                "edges": [
                    {"from": "wp_near", "to": "f1_zoneA", "distance": 3.61},
                ],
            }
        ]
    }


def test_dedup_keeps_first_seen_by_ascending_filename_order():
    """商品コードが複数ファイルにまたがって重複する場合、ファイル名昇順で先に読まれた
    ファイル（＝呼び出し側が渡す rows の並び順）の行が採用されること。"""
    store_map = _store_map_with_all_mid_waypoints()
    rows = [
        ("a_first.csv", {"商品コード": "DUPE1", "商品名": "先勝ち商品", "価格（税込）": "1000円",
                          "URL": "https://a", "画像URL": "https://a.jpg", "カテゴリ": "ソファ",
                          "ブランド": "ニトリ"}),
        ("b_second.csv", {"商品コード": "DUPE1", "商品名": "後勝ち商品（採用されないはず）",
                           "価格（税込）": "9999円", "URL": "https://b", "画像URL": "https://b.jpg",
                           "カテゴリ": "椅子・チェア", "ブランド": "ニトリ"}),
        ("b_second.csv", {"商品コード": "UNIQUE1", "商品名": "ユニーク商品", "価格（税込）": "500円",
                           "URL": "https://c", "画像URL": "https://c.jpg", "カテゴリ": "ソファ",
                           "ブランド": "ニトリ"}),
    ]

    result = build_products(rows, store_map)

    assert len(result) == 2
    by_id = {p["product_id"]: p for p in result}
    assert by_id["DUPE1"]["name"] == "先勝ち商品"
    assert by_id["DUPE1"]["price"] == 1000
    assert by_id["DUPE1"]["cat_mid"] == "ソファ"


def test_dedup_ignores_rows_with_empty_product_code():
    store_map = _store_map_with_all_mid_waypoints()
    rows = [
        ("a.csv", {"商品コード": "", "商品名": "コード無し商品", "価格（税込）": "100円",
                    "URL": "", "画像URL": "", "カテゴリ": "ソファ", "ブランド": "ニトリ"}),
        ("a.csv", {"商品コード": "OK1", "商品名": "正常商品", "価格（税込）": "200円",
                    "URL": "", "画像URL": "", "カテゴリ": "ソファ", "ブランド": "ニトリ"}),
    ]

    result = build_products(rows, store_map)

    assert len(result) == 1
    assert result[0]["product_id"] == "OK1"


# ---------------------------------------------------------------------------
# (5) assign_location: store_map 実ノードの floor/x/y/zone を返す
# ---------------------------------------------------------------------------


def test_resolve_waypoint_location_zone_node_letter_matches_id_suffix():
    store_map = _small_store_map()

    location = resolve_waypoint_location("wp_near", store_map)

    assert location["floor"] == 1
    assert location["x"] == 17
    assert location["y"] == 18
    assert location["zone"] == "A"


def test_resolve_waypoint_location_returns_sub_for_subpassage_node_itself():
    store_map = _small_store_map()

    location = resolve_waypoint_location("sub_1", store_map)

    assert location == {"floor": 1, "x": 95, "y": 88, "zone": "SUB"}


def test_resolve_waypoint_location_unknown_id_raises_keyerror():
    store_map = _small_store_map()

    with pytest.raises(KeyError):
        resolve_waypoint_location("does_not_exist", store_map)


def test_resolve_waypoint_location_node_without_zone_connection_raises_valueerror():
    store_map = {
        "floors": [
            {
                "floor": 1,
                "waypoints": [
                    {"id": "isolated", "floor": 1, "x": 1, "y": 1, "type": "商品近傍"},
                ],
                "edges": [],
            }
        ]
    }

    with pytest.raises(ValueError):
        resolve_waypoint_location("isolated", store_map)


def test_assign_location_uses_mid_to_waypoint_mapping():
    """`assign_location` は `MID_TO_WAYPOINT_ID` を介して中分類→実ノードを解決すること。"""
    store_map = _small_store_map()
    # このテストの検証観点は「mid引数から対応するノードのfloor/x/y/zoneが返る」ことなので、
    # 実データの MID_TO_WAYPOINT_ID をこの小さな store_map 用に一時的に差し替えて検証する。
    import ingest.nitori_ingest as ingest_mod

    original_mapping = dict(ingest_mod.MID_TO_WAYPOINT_ID)
    try:
        ingest_mod.MID_TO_WAYPOINT_ID["ソファ"] = "wp_near"
        location = assign_location("ソファ", store_map)
        assert location == {"floor": 1, "x": 17, "y": 18, "zone": "A"}
    finally:
        ingest_mod.MID_TO_WAYPOINT_ID.clear()
        ingest_mod.MID_TO_WAYPOINT_ID.update(original_mapping)


def test_assign_location_unknown_mid_raises_keyerror():
    store_map = _small_store_map()
    with pytest.raises(KeyError):
        assign_location("存在しない中分類", store_map)


def test_mid_to_waypoint_ids_all_resolve_against_real_store_map():
    """実装指示のMID_TO_WAYPOINT_IDの9エントリすべてが、実際の data/store_map.json 上の
    実在ノードとして解決できること（floor 1〜4に分散・zone取得ができること）。
    store_map.json 自体は小さいファイルのため実データを用いる（9,180件の商品データは使わない）。"""
    store_map = json.loads((FIXTURES_DATA_DIR / "store_map.json").read_text(encoding="utf-8"))

    floors_used = set()
    for mid, waypoint_id in MID_TO_WAYPOINT_ID.items():
        location = resolve_waypoint_location(waypoint_id, store_map)
        assert location["floor"] in {1, 2, 3, 4}
        assert isinstance(location["x"], (int, float))
        assert isinstance(location["y"], (int, float))
        if mid in SUB_PASSAGE_MIDS:
            assert location["zone"] == "SUB"
        else:
            assert location["zone"] in {"A", "B", "C", "D"}
        floors_used.add(location["floor"])

    # 9中分類が4フロアへ分散していること。
    assert floors_used == {1, 2, 3, 4}


# ---------------------------------------------------------------------------
# (6) 出力スキーマの完全性
# ---------------------------------------------------------------------------


def test_build_products_output_schema_is_complete():
    store_map = _store_map_with_all_mid_waypoints()
    rows = [
        ("a.csv", {
            "商品コード": "SOFA001",
            "商品名": "ソファ 布張りタイプ (ホワイト)",
            "価格（税込）": "34990～39990円",
            "URL": "https://www.nitori-net.jp/ec/product/SOFA001/",
            "画像URL": "https://example.com/SOFA001.jpg",
            "カテゴリ": "ソファ",
            "ブランド": "ニトリ",
        }),
    ]

    result = build_products(rows, store_map)

    assert len(result) == 1
    record = result[0]
    expected_keys = {
        "product_id", "name", "price", "image_url", "source_url", "brand",
        "cat_large", "cat_mid", "cat_small", "color", "floor", "zone", "x", "y",
        "sub_passage_flag",
    }
    assert set(record.keys()) == expected_keys
    assert record["product_id"] == "SOFA001"
    assert record["name"] == "ソファ 布張りタイプ (ホワイト)"
    assert record["price"] == 34990
    assert record["source_url"] == "https://www.nitori-net.jp/ec/product/SOFA001/"
    assert record["brand"] == "ニトリ"
    assert record["cat_large"] == "家具"
    assert record["cat_mid"] == "ソファ"
    assert record["cat_small"] == "ソファ"
    assert record["color"] == "ホワイト"
    assert record["sub_passage_flag"] is False


def test_build_products_sets_sub_passage_flag_true_for_cushion_and_lighting():
    store_map = _small_store_map()
    import ingest.nitori_ingest as ingest_mod

    original_mapping = dict(ingest_mod.MID_TO_WAYPOINT_ID)
    try:
        ingest_mod.MID_TO_WAYPOINT_ID["クッション・カバー"] = "sub_1"
        rows = [
            ("a.csv", {
                "商品コード": "CUSHION001",
                "商品名": "クッションカバー ネイビー",
                "価格（税込）": "990円",
                "URL": "https://x",
                "画像URL": "https://x.jpg",
                "カテゴリ": "クッション・カバー",
                "ブランド": "ニトリ",
            }),
        ]

        result = build_products(rows, store_map)

        assert result[0]["sub_passage_flag"] is True
        assert result[0]["zone"] == "SUB"
    finally:
        ingest_mod.MID_TO_WAYPOINT_ID.clear()
        ingest_mod.MID_TO_WAYPOINT_ID.update(original_mapping)


def test_build_products_raises_on_unknown_category():
    store_map = _small_store_map()
    rows = [
        ("a.csv", {"商品コード": "X1", "商品名": "謎商品", "価格（税込）": "100円",
                    "URL": "", "画像URL": "", "カテゴリ": "未知カテゴリ", "ブランド": "ニトリ"}),
    ]

    with pytest.raises(KeyError):
        build_products(rows, store_map)


# ---------------------------------------------------------------------------
# run(): CSV→products.json のI/Oオーケストレーション（隔離ディレクトリでの小規模スモーク）
# ---------------------------------------------------------------------------


def test_run_end_to_end_on_small_isolated_source_dir(tmp_path):
    """`run()` を隔離ディレクトリに対して実行し、CSV読込→変換→products.json書き出しが
    一気通貫で動作すること（実データではなく、小さな自作CSV/store_mapで検証）。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (tmp_path / "store_map.json").write_text(
        json.dumps(_store_map_with_all_mid_waypoints()), encoding="utf-8"
    )

    header = "商品コード,商品名,価格（税込）,URL,画像URL,カテゴリ,ブランド\n"
    (source_dir / "nitori_sofa_products.csv").write_text(
        header + "S001,テストソファ ホワイト,10000円,https://x,https://x.jpg,ソファ,ニトリ\n",
        encoding="utf-8-sig",
    )
    (source_dir / "nitori_chair_products_excluding_sofa.csv").write_text(
        header + "C001,テストチェア ブラック,5000円,https://x,https://x.jpg,椅子・チェア,ニトリ\n",
        encoding="utf-8-sig",
    )

    summary = run(data_dir=tmp_path)

    assert summary["total"] == 2
    assert summary["by_mid"] == {"ソファ": 1, "椅子・チェア": 1}

    products = json.loads((tmp_path / "products.json").read_text(encoding="utf-8"))
    assert len(products) == 2
    ids = {p["product_id"] for p in products}
    assert ids == {"S001", "C001"}


def test_run_is_byte_reproducible(tmp_path):
    """(4) 同一入力に対して run() を2回実行すればバイト単位で同一出力になること（再現性）。"""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    for target in (dir_a, dir_b):
        target.mkdir()
        (target / "source").mkdir()
        (target / "store_map.json").write_text(
            json.dumps(_store_map_with_all_mid_waypoints()), encoding="utf-8"
        )
        header = "商品コード,商品名,価格（税込）,URL,画像URL,カテゴリ,ブランド\n"
        (target / "source" / "nitori_sofa_products.csv").write_text(
            header + "S001,テストソファ,10000円,https://x,https://x.jpg,ソファ,ニトリ\n",
            encoding="utf-8-sig",
        )

    run(data_dir=dir_a)
    run(data_dir=dir_b)

    assert (dir_a / "products.json").read_text(encoding="utf-8") == (
        dir_b / "products.json"
    ).read_text(encoding="utf-8")


def _store_map_with_all_mid_waypoints() -> dict:
    """`MID_TO_WAYPOINT_ID` の全エントリを解決可能にする小さな店舗マップ（テスト専用）。"""
    waypoints = [{"id": "z_a", "floor": 1, "x": 20, "y": 20, "type": "ゾーン"}]
    edges = []
    for mid, wp_id in MID_TO_WAYPOINT_ID.items():
        if mid in SUB_PASSAGE_MIDS:
            waypoints.append({"id": wp_id, "floor": 1, "x": 90, "y": 90, "type": "サブ通路"})
        else:
            if wp_id not in {w["id"] for w in waypoints}:
                waypoints.append({"id": wp_id, "floor": 1, "x": 10, "y": 10, "type": "商品近傍"})
                edges.append({"from": wp_id, "to": "z_a", "distance": 1.0})
    return {"floors": [{"floor": 1, "waypoints": waypoints, "edges": edges}]}
