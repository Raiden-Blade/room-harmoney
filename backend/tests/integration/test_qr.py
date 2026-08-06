"""`GET /api/qr/{qr_id}`（17章）の結合テスト。"""
from __future__ import annotations


def test_resolve_product_qr_returns_expected_shape(client):
    response = client.get("/api/qr/QR-PRODUCT-P001")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "type": "product",
        "product_id": "P001",
        "position": {"floor": 1, "x": 17, "y": 18},
        "direct_url": "https://roomharmony.example.com/r/QR-PRODUCT-P001",
    }


def test_resolve_entrance_qr_has_no_product_id(client):
    response = client.get("/api/qr/QR-ENTRANCE-001")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "entrance"
    assert body["product_id"] is None
    assert body["position"] == {"floor": 1, "x": 3, "y": 50}


def test_resolve_unknown_qr_returns_404(client):
    response = client.get("/api/qr/QR-NOT-REGISTERED")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "QR_NOT_FOUND"
