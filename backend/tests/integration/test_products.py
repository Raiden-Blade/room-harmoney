"""`GET /api/products/{product_id}`（17章）の結合テスト。"""
from __future__ import annotations


def test_get_known_product_returns_full_detail(client):
    response = client.get("/api/products/P001")

    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == "P001"
    assert body["cat_large"] == "リビング"
    assert body["cat_mid"] == "ソファ"
    assert body["color"] == "ナチュラル"
    assert body["price"] == 39900
    assert "image_url" in body
    assert body["floor"] == 1
    assert body["zone"] == "A"


def test_get_unknown_product_returns_404(client):
    response = client.get("/api/products/DOES-NOT-EXIST")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "PRODUCT_NOT_FOUND"
