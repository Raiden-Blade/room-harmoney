"""`POST /api/session`（17章）の結合テスト。"""
from __future__ import annotations

from app.experiment import CONTROL, TREATMENT


def test_create_session_with_valid_qr_returns_expected_shape(client):
    response = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"session_id", "start", "floor", "experiment_group"}
    assert body["floor"] == 1
    assert body["start"] == {"floor": 1, "x": 3, "y": 50}
    assert body["experiment_group"] in {TREATMENT, CONTROL}
    assert isinstance(body["session_id"], str) and body["session_id"]


def test_create_session_with_product_qr_uses_product_qr_coordinates(client):
    response = client.post("/api/session", json={"qr_id": "QR-PRODUCT-P001"})

    assert response.status_code == 200
    body = response.json()
    assert body["start"] == {"floor": 1, "x": 17, "y": 18}


def test_create_session_with_unknown_qr_returns_404(client):
    response = client.post("/api/session", json={"qr_id": "QR-DOES-NOT-EXIST"})

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "QR_NOT_FOUND"
    assert "message" in body


def test_create_session_records_session_start_event(client, store):
    response = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
    session_id = response.json()["session_id"]

    events = store.list_events(session_id=session_id)

    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "session_start"
    assert event["session_id"] == session_id
    assert event["experiment_group"] == response.json()["experiment_group"]
    payload = event["payload"]
    assert payload["qr_id"] == "QR-ENTRANCE-001"
    assert payload["qr_type"] == "entrance"
    assert payload["floor"] == 1
    assert payload["store_id"]
    assert payload["experiment_group"] == response.json()["experiment_group"]


def test_create_session_persists_session_row(client, store):
    response = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
    session_id = response.json()["session_id"]

    session_row = store.get_session(session_id)

    assert session_row is not None
    assert session_row["qr_id"] == "QR-ENTRANCE-001"
    assert session_row["floor"] == 1
