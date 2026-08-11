"""`GET /api/qr/{qr_id}` の商品QRパターン解決フォールバック（段階B2）の結合テスト。

段階B2注記: 実データ（約9,180件）では `data/qr_codes.json` に商品QRを全件明示列挙しない
方針を採るため、`QR-PRODUCT-<商品コード>` 形式の qr_id は明示エントリが無くても
`ProductRepository`（商品番号索引）経由でその場で解決される
（`app.repositories.QrRepository._resolve_product_pattern` 参照）。

フィクスチャ（`backend/tests/fixtures/data/qr_codes.json`）は `product_id` ベースの
qr_id（`QR-PRODUCT-P001` 等）を明示エントリとして持つが、`商品コード`ベースの
qr_id（`QR-PRODUCT-<product_code>`）は明示エントリとして存在しない。これを使って
フォールバック経路のみを検証する（フィクスチャ自体は変更しない）。
"""
from __future__ import annotations

from dataio import load_json_list

from tests.fixtures import DATA_DIR as FIXTURES_DATA_DIR


def _expected_p001_code() -> str:
    products = load_json_list("products.json", data_dir=FIXTURES_DATA_DIR)
    p001 = next(p for p in products if p["product_id"] == "P001")
    return p001["product_code"]


def test_resolve_qr_by_product_code_pattern_without_explicit_entry(client):
    code = _expected_p001_code()
    qr_id = f"QR-PRODUCT-{code}"

    response = client.get(f"/api/qr/{qr_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "product"
    assert body["product_id"] == "P001"
    assert body["position"] == {"floor": 1, "x": 17, "y": 18}
    assert body["direct_url"] == f"https://roomharmony.example.com/r/{qr_id}"


def test_resolve_qr_by_explicit_product_id_still_works(client):
    """フィクスチャ既存の明示エントリ（product_id ベース）は従来どおり解決できる（回帰確認）。"""
    response = client.get("/api/qr/QR-PRODUCT-P001")

    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == "P001"
    assert body["direct_url"] == "https://roomharmony.example.com/r/QR-PRODUCT-P001"


def test_resolve_qr_by_unknown_product_code_pattern_still_returns_404(client):
    response = client.get("/api/qr/QR-PRODUCT-99-99-99-9999")

    assert response.status_code == 404
    assert response.json()["code"] == "QR_NOT_FOUND"


def test_product_code_endpoint_falls_back_to_pattern_when_no_explicit_qr(client):
    """`GET /api/product-code/{code}` 側も、qr_codes.json に明示の商品QRが無い商品コード
    ベースの qr_id で最終的に解決できることを、`get_by_product_id` を一時的に空にして確認する
    （実データ相当の状況＝明示エントリ無しを模擬）。
    """
    from app.config import Settings
    from app.dependencies import get_qr_repo
    from app.main import app
    from app.repositories import ProductRepository, QrRepository

    code = _expected_p001_code()

    # 実データ相当（qr_codes.json に商品QRの明示エントリが無い状態）を模擬するため、
    # product_repo だけを持つ空の QrRepository に差し替える。
    settings = Settings(data_dir=FIXTURES_DATA_DIR)
    product_repo = ProductRepository.from_data_dir(data_dir=settings.data_dir)
    empty_qr_repo = QrRepository([], product_repo=product_repo)

    app.dependency_overrides[get_qr_repo] = lambda: empty_qr_repo
    try:
        response = client.get(f"/api/product-code/{code}")
    finally:
        del app.dependency_overrides[get_qr_repo]

    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == "P001"
    assert body["qr_id"] == f"QR-PRODUCT-{code}"
    assert body["position"] == {"floor": 1, "x": 17, "y": 18}
