"""`GET /api/coordinates/{coordinate_id}`（17章）の結合テスト。"""
from __future__ import annotations


def test_get_known_coordinate_returns_products_and_price(client):
    response = client.get("/api/coordinates/C001")

    assert response.status_code == 200
    body = response.json()
    assert body["coordinate_id"] == "C001"
    assert body["total_price_estimate"] == 70690
    assert "image_url" in body
    product_ids = {p["product_id"] for p in body["products"]}
    assert product_ids == {"P001", "P003", "P007", "P009"}


def test_get_unknown_coordinate_returns_404(client):
    response = client.get("/api/coordinates/DOES-NOT-EXIST")

    assert response.status_code == 404
    assert response.json()["code"] == "COORDINATE_NOT_FOUND"


def test_get_coordinate_with_session_id_records_coordinate_view_event(
    client, active_session, store
):
    response = client.get(
        "/api/coordinates/C001", params={"session_id": active_session["session_id"]}
    )

    assert response.status_code == 200

    events = store.list_events(session_id=active_session["session_id"])
    coordinate_view_events = [e for e in events if e["event_type"] == "coordinate_view"]

    assert len(coordinate_view_events) == 1
    assert coordinate_view_events[0]["payload"]["coordinate_id"] == "C001"
    assert coordinate_view_events[0]["experiment_group"] == active_session["experiment_group"]


def test_get_coordinate_without_session_id_does_not_error(client):
    """coordinates はコアの来店ロック対象外（実装指示の明示仕様に基づく）。session_id無しでも200。"""
    response = client.get("/api/coordinates/C001")

    assert response.status_code == 200
