"""`GET /api/store-map/{floor}`（17章）の結合テスト。"""
from __future__ import annotations


def test_get_floor_1_returns_zones_and_waypoints(client):
    response = client.get("/api/store-map/1")

    assert response.status_code == 200
    body = response.json()
    assert body["floor"] == 1
    assert "floorplan" in body
    assert "zones" in body
    assert "waypoints" in body
    assert "sub_passages" in body
    assert len(body["waypoints"]) > 0


def test_get_out_of_range_floor_returns_404(client):
    response = client.get("/api/store-map/99")

    assert response.status_code == 404
    assert response.json()["code"] == "FLOOR_NOT_FOUND"
