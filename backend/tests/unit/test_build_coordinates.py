"""暫定コーディネート生成バッチ（`backend/ingest/build_coordinates.py`）の単体テスト。

段階B2ゲート（実商品データ9,180件・9中分類への差し替え）の重点観点:
  (1) 決定性（同一入力から常に同一出力）
  (2) 構成 product_id が入力の実商品に実在する（参照整合）
  (3) total_price_estimate が構成商品の price 合計と一致する
  (4) 商品が不足している中分類を指定した場合はサイレントに無視せず例外にする
  (5) `run()` が実行するとファイル（`data/coordinates.json` 相当）が書き出され、
      構成商品が products.json（フィクスチャ）に実在する
"""
from __future__ import annotations

import json

import pytest

from dataio import load_json_list
from ingest.build_coordinates import CoordinateSpec, Pick, build_coordinates, run

from tests.fixtures import DATA_DIR as FIXTURES_DATA_DIR


def _small_products() -> list[dict]:
    """テスト用の小規模商品セット（cat_mid: ソファ2件・テーブル1件）。"""
    return [
        {"product_id": "S002", "cat_mid": "ソファ", "price": 5000},
        {"product_id": "S001", "cat_mid": "ソファ", "price": 3000},
        {"product_id": "T001", "cat_mid": "テーブル", "price": 10000},
    ]


def test_build_coordinates_selects_product_id_ascending_order():
    """(1)(2) 各中分類は product_id 昇順で先頭から選ばれること（S001が先、S002が後）。"""
    specs = (
        CoordinateSpec(
            coordinate_id="X001",
            name="テスト",
            theme="テスト",
            picks=(Pick("ソファ", 0, 2),),
        ),
    )

    coordinates = build_coordinates(_small_products(), specs)

    assert len(coordinates) == 1
    assert coordinates[0]["product_ids"] == ["S001", "S002"]


def test_build_coordinates_computes_total_price_from_member_products():
    """(3) total_price_estimate は構成商品の price 合計と一致する。"""
    specs = (
        CoordinateSpec(
            coordinate_id="X001",
            name="テスト",
            theme="テスト",
            picks=(Pick("ソファ", 0, 1), Pick("テーブル", 0, 1)),
        ),
    )

    coordinates = build_coordinates(_small_products(), specs)

    assert coordinates[0]["product_ids"] == ["S001", "T001"]
    assert coordinates[0]["total_price_estimate"] == 3000 + 10000


def test_build_coordinates_is_deterministic_same_input_same_output():
    """(1) 同一入力を2回計算しても、バイト単位で同一の出力になること（再現性）。"""
    specs = (
        CoordinateSpec(
            coordinate_id="X001",
            name="テスト",
            theme="テスト",
            picks=(Pick("ソファ", 0, 2), Pick("テーブル", 0, 1)),
        ),
    )
    products = _small_products()

    result_1 = build_coordinates(products, specs)
    result_2 = build_coordinates(products, specs)

    assert result_1 == result_2
    assert json.dumps(result_1, ensure_ascii=False) == json.dumps(result_2, ensure_ascii=False)


def test_build_coordinates_includes_image_url_and_theme_fields():
    """出力スキーマが coordinates.json の既存列（coordinate_id/name/theme/product_ids/
    image_url/total_price_estimate）を満たすこと。"""
    specs = (
        CoordinateSpec(
            coordinate_id="X001",
            name="テストコーデ",
            theme="テストテーマ",
            picks=(Pick("ソファ", 0, 1),),
        ),
    )

    coordinates = build_coordinates(_small_products(), specs)

    expected_columns = {
        "coordinate_id",
        "name",
        "theme",
        "product_ids",
        "image_url",
        "total_price_estimate",
    }
    assert set(coordinates[0].keys()) == expected_columns
    assert coordinates[0]["name"] == "テストコーデ"
    assert coordinates[0]["theme"] == "テストテーマ"
    assert "X001" in coordinates[0]["image_url"]


def test_build_coordinates_raises_when_category_has_insufficient_products():
    """(4) 指定件数に対して実商品が不足する場合、サイレントに無視せず例外にすること。"""
    specs = (
        CoordinateSpec(
            coordinate_id="X001",
            name="テスト",
            theme="テスト",
            picks=(Pick("ソファ", 0, 5),),  # ソファは2件しかない
        ),
    )

    with pytest.raises(ValueError):
        build_coordinates(_small_products(), specs)


def test_build_coordinates_raises_when_category_is_unknown():
    """(4) 未知の中分類（0件）を指定した場合も例外にすること。"""
    specs = (
        CoordinateSpec(
            coordinate_id="X001",
            name="テスト",
            theme="テスト",
            picks=(Pick("存在しない中分類", 0, 1),),
        ),
    )

    with pytest.raises(ValueError):
        build_coordinates(_small_products(), specs)


def test_run_generates_file_referencing_only_existing_products(tmp_path):
    """(5) 参照整合: run() が生成した coordinates.json の product_ids が
    products.json（フィクスチャ）に実在すること。

    段階A同様、フィクスチャ（`data/` サンプルの固定コピー）を入力に一時ディレクトリへ
    生成して検証する（本番の data/coordinates.json を書き換えないため tmp_path を使う）。

    注記: `backend/tests/fixtures/data/products.json` は段階Aで切り離した「サンプルの
    固定コピー」であり、旧サンプルの中分類体系（"ソファ"/"リビングテーブル" 等）のままで
    実データの9中分類（"テーブル"/"椅子・チェア" 等）とは異なる。よってモジュール既定の
    `COORDINATE_SPECS`（実データ前提）はここでは使わず、フィクスチャに実在する中分類で
    構成したテスト用 `specs` を明示的に渡す（フィクスチャは変更しない）。
    """
    fixture_products_path = FIXTURES_DATA_DIR / "products.json"
    (tmp_path / "products.json").write_text(
        fixture_products_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    fixture_specs = (
        CoordinateSpec(
            coordinate_id="X001",
            name="フィクスチャ検証用",
            theme="テスト",
            picks=(Pick("ソファ", 0, 1), Pick("リビングテーブル", 0, 1)),
        ),
    )

    summary = run(data_dir=tmp_path, specs=fixture_specs)

    assert summary["generated"] > 0

    generated = json.loads((tmp_path / "coordinates.json").read_text(encoding="utf-8"))
    assert len(generated) == summary["generated"]

    products = load_json_list("products.json", data_dir=FIXTURES_DATA_DIR)
    product_ids = {p["product_id"] for p in products}

    for coordinate in generated:
        assert coordinate["product_ids"], f"空のコーディネート: {coordinate['coordinate_id']}"
        for pid in coordinate["product_ids"]:
            assert pid in product_ids, f"未知の product_id: {pid}"
        prices_by_id = {p["product_id"]: p["price"] for p in products}
        expected_total = sum(prices_by_id[pid] for pid in coordinate["product_ids"])
        assert coordinate["total_price_estimate"] == expected_total
