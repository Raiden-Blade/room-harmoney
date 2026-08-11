"""サンプルデータ（data/ 配下）の参照整合性・グラフ連結性の単体テスト。

11章サンプルデータ仕様 / DESIGN.md データモデルに基づき、以下を検証する。
- coordinates.json の product_ids が products.json に実在する
- co_purchase.json の cat_mid_a/b が products.json の cat_mid に存在する
- 商品数が30〜50点の範囲内、sub_passage_flag が一部に立っている
- co_purchase に「リフト高×併売率低（伸びしろ）」ペアが意図通り含まれる
- store_map.json の全ウェイポイントが1つの連結成分になっている（4フロアが階段/EVで繋がる）
- 実データ経由で HybridRecommender / RouteGraphBuilder が例外なく動作する（スモーク）
"""
from dataio import load_json_list
from recommender.hybrid import HybridRecommender
from routing import RouteGraphBuilder

from tests.fixtures import DATA_DIR as FIXTURES_DATA_DIR

# 段階A: このテストは「サンプルデータの仕様（30〜50点等）」を検証するものであり、
# ライブの `data/`（この後、実データ約9,180件へ差し替え予定）ではなく、固定フィクスチャ
# （リファクタ時点の `data/*.json` サンプルのコピー）を参照する。


def test_products_count_and_sub_passage_flag_within_spec():
    products = load_json_list("products.json", data_dir=FIXTURES_DATA_DIR)

    assert 30 <= len(products) <= 50
    assert any(p["sub_passage_flag"] is True for p in products)
    assert any(p["sub_passage_flag"] is False for p in products)
    # 複数の大分類・中分類・色をまたぐこと
    assert len({p["cat_large"] for p in products}) >= 3
    assert len({p["cat_mid"] for p in products}) >= 5
    assert len({p["color"] for p in products}) >= 3


def test_coordinates_product_ids_reference_existing_products():
    products = load_json_list("products.json", data_dir=FIXTURES_DATA_DIR)
    coordinates = load_json_list("coordinates.json", data_dir=FIXTURES_DATA_DIR)

    product_ids = {p["product_id"] for p in products}
    assert 3 <= len(coordinates) <= 5

    for coord in coordinates:
        assert 3 <= len(coord["product_ids"]) <= 6
        for pid in coord["product_ids"]:
            assert pid in product_ids, f"{coord['coordinate_id']} references unknown product {pid}"


def test_co_purchase_cat_mids_reference_existing_product_categories():
    products = load_json_list("products.json", data_dir=FIXTURES_DATA_DIR)
    co_purchase = load_json_list("co_purchase.json", data_dir=FIXTURES_DATA_DIR)

    cat_mids = {p["cat_mid"] for p in products}
    assert len(co_purchase) > 0

    for row in co_purchase:
        assert row["cat_mid_a"] in cat_mids
        assert row["cat_mid_b"] in cat_mids


def test_co_purchase_has_intentional_high_lift_low_corate_pairs():
    """「リフトは高いのに現状の併売率が低い」ペアが数組、意図的に含まれていること（5.1章）。"""
    co_purchase = load_json_list("co_purchase.json", data_dir=FIXTURES_DATA_DIR)

    flagged = [row for row in co_purchase if row["high_lift_low_corate"] is True]
    assert 2 <= len(flagged) <= 10

    non_flagged_lifts = [row["lift"] for row in co_purchase if not row["high_lift_low_corate"]]
    non_flagged_supports = [row["support"] for row in co_purchase if not row["high_lift_low_corate"]]

    for row in flagged:
        # 伸びしろペアは、非フラグ群と比べて相対的に「高リフト・低併売率」であること
        assert row["lift"] > (max(non_flagged_lifts) if non_flagged_lifts else 0)
        assert row["support"] < (min(non_flagged_supports) if non_flagged_supports else 1)


def test_store_map_all_waypoints_are_connected_across_four_floors():
    """4フロアの全ウェイポイントが階段/EV経由で1つの連結成分になっていること。"""
    store_map = _load_store_map_dict()
    builder = RouteGraphBuilder.from_store_map(store_map)

    node_ids = builder.node_ids()
    assert len(node_ids) > 0

    # 起点(1F入口)から到達できるノード数が全体と一致すれば連結。
    import networkx as nx

    reachable = nx.node_connected_component(builder._graph, "f1_entrance")  # noqa: SLF001 (テストでの内部検証)
    assert len(reachable) == len(node_ids)

    floors_present = {builder.get_node(n)["floor"] for n in node_ids}
    assert floors_present == {1, 2, 3, 4}


def test_real_sample_data_route_from_entrance_to_floor4_product_resolves():
    """実データで 1F入口 → 4F商品 の経路（フロア横断）が例外なく解けること（スモーク）。"""
    store_map = _load_store_map_dict()
    products = load_json_list("products.json", data_dir=FIXTURES_DATA_DIR)
    builder = RouteGraphBuilder.from_store_map(store_map)

    floor4_product = next(p for p in products if p["floor"] == 4)
    start = builder.nearest_node(floor=1, x=3, y=50, node_type="入口")
    goal = builder.nearest_node(floor=4, x=floor4_product["x"], y=floor4_product["y"], node_type="商品近傍")

    result = builder.shortest_path(start, goal)

    assert result.floors[0] == 1
    assert result.floors[-1] == 4
    assert result.total_distance > 0


def test_real_sample_data_recommender_smoke():
    """実データで HybridRecommender.from_data_dir() が例外なく動作すること（スモーク）。"""
    rec = HybridRecommender.from_data_dir(data_dir=FIXTURES_DATA_DIR)
    products = load_json_list("products.json", data_dir=FIXTURES_DATA_DIR)

    sample_product_id = products[0]["product_id"]
    result = rec.recommend(sample_product_id)

    assert result.product_found is True
    # related/coordinates の型が保たれていること（空でも良いが例外にならないこと）
    assert isinstance(result.related, list)
    assert isinstance(result.coordinates, list)


def _load_store_map_dict() -> dict:
    import json

    path = FIXTURES_DATA_DIR / "store_map.json"
    return json.loads(path.read_text(encoding="utf-8"))
