"""`GET /api/product-code/{code}`（新機能: 商品番号による直接遷移）の結合テスト。

実データ（data/products.json / data/qr_codes.json。`batch.product_codes` 実行済み）を前提に、
P001 の商品番号で解決できることを確認する。P001 の product_code は
`backend/batch/product_codes.py` の階層採番により決定的に定まるため、テストでは
実データを読んで期待値を動的に取得する（ハードコードによる将来の採番変更時の
無用な壊れを避けるため）。
"""
from __future__ import annotations

from dataio import load_json_list

from tests.fixtures import DATA_DIR as FIXTURES_DATA_DIR


def _expected_p001_code() -> str:
    # 段階A: `client` フィクスチャ（DIチェーン経由でフィクスチャを参照）と整合させるため、
    # ここでの期待値算出も同じフィクスチャ（`data/` サンプルの固定コピー）から読む。
    products = load_json_list("products.json", data_dir=FIXTURES_DATA_DIR)
    p001 = next(p for p in products if p["product_id"] == "P001")
    assert p001.get("product_code"), "products.json に product_code が付与されていません。先に `py -m batch.product_codes` を実行してください。"
    return p001["product_code"]


def test_resolve_by_hyphenated_code_returns_expected_shape(client):
    code = _expected_p001_code()

    response = client.get(f"/api/product-code/{code}")

    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == "P001"
    assert body["qr_id"] == "QR-PRODUCT-P001"
    assert body["position"] == {"floor": 1, "x": 17, "y": 18}
    assert body["product_code"] == code


def test_resolve_by_digits_only_code_resolves_to_same_product(client):
    """ハイフンを除いた数字9桁の入力でも同一商品に解決できること。"""
    code = _expected_p001_code()
    digits_only = code.replace("-", "")
    assert digits_only != code

    response_hyphen = client.get(f"/api/product-code/{code}")
    response_digits = client.get(f"/api/product-code/{digits_only}")

    assert response_hyphen.status_code == 200
    assert response_digits.status_code == 200
    assert response_hyphen.json() == response_digits.json()


def test_resolve_unknown_code_returns_404_with_clear_code_and_message(client):
    response = client.get("/api/product-code/99-99-99-999")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "PRODUCT_CODE_NOT_FOUND"
    assert "message" in body and body["message"]


def test_resolve_malformed_code_returns_404_not_500(client):
    """数字を含まない/短すぎる入力でも例外を起こさず404で明確に返すこと（19章エッジケース）。"""
    response = client.get("/api/product-code/not-a-code")

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_CODE_NOT_FOUND"


def test_get_product_detail_includes_product_code(client):
    """`GET /api/products/{id}` のレスポンスに product_code が含まれること
    （商品詳細画面での番号表示のため）。"""
    response = client.get("/api/products/P001")

    assert response.status_code == 200
    body = response.json()
    assert body["product_code"] == _expected_p001_code()
