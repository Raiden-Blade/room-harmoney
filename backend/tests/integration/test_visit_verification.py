"""来店検証の高度化（フェーズ3-B / DECISIONS.md #7）の結合テスト。

- 既定モード(qr): 位置なしセッションでも recommendations/route が従来どおり動く（無回帰）。
- 拡張モード(qr+geofence / qr+wifi): `VISIT_VERIFICATION_MODE` を差し替えたときのみ、
  位置/SSIDシグナルの検証が来店ロックに反映されることを検証する。
- プライバシー（9章）: location/wifi_ssid が `events`（効果ログ）に一切保存されないこと。
"""
from __future__ import annotations

import pytest

from app.config import Settings, get_settings
from app.main import app

# 目黒通り店（DECISIONS.md #4）付近の開発用ダミー座標（config.py の既定値と同一）。
STORE_LAT = 35.6203
STORE_LNG = 139.6883
OUTSIDE_LAT = 35.0
OUTSIDE_LNG = 135.0
ALLOWED_SSID = "Nitori-Free-Wifi"


@pytest.fixture()
def with_mode(client):
    """`VISIT_VERIFICATION_MODE` を差し替えた `client` を使うためのヘルパー。

    `client` フィクスチャ自体のteardown（`app.dependency_overrides.clear()`）が
    最終的に呼ばれるため、ここで明示的に元へ戻さなくても後続テストへは波及しない。
    """

    def _configure(mode: str):
        app.dependency_overrides[get_settings] = lambda: Settings(
            visit_verification_mode=mode
        )
        return client

    return _configure


# -- 既定モード(qr)の無回帰確認 ---------------------------------------------------------
def test_default_qr_mode_without_location_signals_still_works(client):
    """位置情報を一切送らないセッションでも、既定モード(qr)なら中核機能が使える（無回帰）。"""
    session_resp = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    rec_resp = client.get(
        "/api/recommendations", params={"product_id": "P001", "session_id": session_id}
    )
    assert rec_resp.status_code == 200

    route_resp = client.get(
        "/api/route",
        params={"from_qr": "QR-ENTRANCE-001", "to_product": "P001", "session_id": session_id},
    )
    assert route_resp.status_code == 200


def test_default_qr_mode_even_with_location_signals_still_ignores_them(client):
    """既定モード(qr)は location/wifi_ssid を送っても無視し、判定に影響しない。"""
    session_resp = client.post(
        "/api/session",
        json={
            "qr_id": "QR-ENTRANCE-001",
            "location": {"lat": OUTSIDE_LAT, "lng": OUTSIDE_LNG},
            "wifi_ssid": "Totally-Unrelated-Wifi",
        },
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    rec_resp = client.get(
        "/api/recommendations", params={"product_id": "P001", "session_id": session_id}
    )
    assert rec_resp.status_code == 200


# -- qr+geofence モード -----------------------------------------------------------------
def test_geofence_mode_inside_store_returns_200(with_mode):
    configured_client = with_mode("qr+geofence")
    session_resp = configured_client.post(
        "/api/session",
        json={"qr_id": "QR-ENTRANCE-001", "location": {"lat": STORE_LAT, "lng": STORE_LNG}},
    )
    session_id = session_resp.json()["session_id"]

    rec_resp = configured_client.get(
        "/api/recommendations", params={"product_id": "P001", "session_id": session_id}
    )
    assert rec_resp.status_code == 200


def test_geofence_mode_outside_store_returns_409(with_mode):
    configured_client = with_mode("qr+geofence")
    session_resp = configured_client.post(
        "/api/session",
        json={"qr_id": "QR-ENTRANCE-001", "location": {"lat": OUTSIDE_LAT, "lng": OUTSIDE_LNG}},
    )
    session_id = session_resp.json()["session_id"]

    rec_resp = configured_client.get(
        "/api/recommendations", params={"product_id": "P001", "session_id": session_id}
    )
    assert rec_resp.status_code == 409
    assert rec_resp.json()["code"] == "VISIT_NOT_VERIFIED"


def test_geofence_mode_missing_location_returns_409(with_mode):
    configured_client = with_mode("qr+geofence")
    session_resp = configured_client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
    session_id = session_resp.json()["session_id"]

    rec_resp = configured_client.get(
        "/api/recommendations", params={"product_id": "P001", "session_id": session_id}
    )
    assert rec_resp.status_code == 409
    assert rec_resp.json()["code"] == "VISIT_NOT_VERIFIED"


def test_geofence_mode_applies_to_route_endpoint_too(with_mode):
    configured_client = with_mode("qr+geofence")
    session_resp = configured_client.post(
        "/api/session",
        json={"qr_id": "QR-ENTRANCE-001", "location": {"lat": OUTSIDE_LAT, "lng": OUTSIDE_LNG}},
    )
    session_id = session_resp.json()["session_id"]

    route_resp = configured_client.get(
        "/api/route",
        params={"from_qr": "QR-ENTRANCE-001", "to_product": "P001", "session_id": session_id},
    )
    assert route_resp.status_code == 409
    assert route_resp.json()["code"] == "VISIT_NOT_VERIFIED"


# -- qr+wifi モード ----------------------------------------------------------------------
def test_wifi_mode_allowed_ssid_returns_200(with_mode):
    configured_client = with_mode("qr+wifi")
    session_resp = configured_client.post(
        "/api/session", json={"qr_id": "QR-ENTRANCE-001", "wifi_ssid": ALLOWED_SSID}
    )
    session_id = session_resp.json()["session_id"]

    rec_resp = configured_client.get(
        "/api/recommendations", params={"product_id": "P001", "session_id": session_id}
    )
    assert rec_resp.status_code == 200


def test_wifi_mode_disallowed_ssid_returns_409(with_mode):
    configured_client = with_mode("qr+wifi")
    session_resp = configured_client.post(
        "/api/session", json={"qr_id": "QR-ENTRANCE-001", "wifi_ssid": "Random-Other-Wifi"}
    )
    session_id = session_resp.json()["session_id"]

    rec_resp = configured_client.get(
        "/api/recommendations", params={"product_id": "P001", "session_id": session_id}
    )
    assert rec_resp.status_code == 409
    assert rec_resp.json()["code"] == "VISIT_NOT_VERIFIED"


def test_wifi_mode_missing_ssid_returns_409(with_mode):
    configured_client = with_mode("qr+wifi")
    session_resp = configured_client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
    session_id = session_resp.json()["session_id"]

    rec_resp = configured_client.get(
        "/api/recommendations", params={"product_id": "P001", "session_id": session_id}
    )
    assert rec_resp.status_code == 409
    assert rec_resp.json()["code"] == "VISIT_NOT_VERIFIED"


# -- プライバシー: location/wifi_ssid は events に保存しない -----------------------------
def test_location_and_wifi_signals_are_never_persisted_in_events(with_mode, store):
    configured_client = with_mode("qr+geofence")
    session_resp = configured_client.post(
        "/api/session",
        json={
            "qr_id": "QR-ENTRANCE-001",
            "location": {"lat": STORE_LAT, "lng": STORE_LNG},
            "wifi_ssid": ALLOWED_SSID,
        },
    )
    session_id = session_resp.json()["session_id"]

    configured_client.get(
        "/api/recommendations", params={"product_id": "P001", "session_id": session_id}
    )
    configured_client.get(
        "/api/route",
        params={"from_qr": "QR-ENTRANCE-001", "to_product": "P001", "session_id": session_id},
    )

    events = store.list_events(session_id=session_id)
    assert len(events) >= 1
    forbidden_keys = {"location", "location_lat", "location_lng", "wifi_ssid", "lat", "lng", "ssid"}
    for event in events:
        payload_keys = set(event["payload"].keys())
        assert not (payload_keys & forbidden_keys), (
            f"event_type={event['event_type']} payload contains forbidden key(s): "
            f"{payload_keys & forbidden_keys}"
        )
        # payload全体を文字列化しても、報告した実座標・SSID値そのものを含まないことを確認。
        payload_str = str(event["payload"])
        assert str(STORE_LAT) not in payload_str
        assert str(STORE_LNG) not in payload_str
        assert ALLOWED_SSID not in payload_str


def test_location_and_wifi_are_persisted_in_sessions_table_for_verification(with_mode, store):
    """判定用に `sessions` テーブルへは保持されること（events には出さないだけ）。"""
    configured_client = with_mode("qr+geofence")
    session_resp = configured_client.post(
        "/api/session",
        json={
            "qr_id": "QR-ENTRANCE-001",
            "location": {"lat": STORE_LAT, "lng": STORE_LNG},
            "wifi_ssid": ALLOWED_SSID,
        },
    )
    session_id = session_resp.json()["session_id"]

    session_row = store.get_session(session_id)
    assert session_row["location_lat"] == pytest.approx(STORE_LAT)
    assert session_row["location_lng"] == pytest.approx(STORE_LNG)
    assert session_row["wifi_ssid"] == ALLOWED_SSID
