"""`GET /api/admin/kpi`（フェーズ2-B1 A/B×KPI集計API）の結合テスト。

17章「管理系は認証必須」の認証（`X-Admin-Token`）、`app/analytics.py` の集計結果が
実際のDB（隔離SQLite）経由でも正しく出ること、POS突合スロットの有無切り替えを検証する。
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.dependencies import get_pos_metrics, get_settings
from app.experiment import CONTROL, TREATMENT
from app.main import app

ADMIN_TOKEN = "test-admin-token-abc123"


@pytest.fixture(autouse=True)
def _fixed_admin_token():
    """管理トークンをテスト内で決定的な値に固定する（実行環境のADMIN_API_TOKEN設定に
    依存させないため。`get_settings` は他ルータからも参照されるため、admin_api_token
    以外は既定値のまま差し替える）。"""
    app.dependency_overrides[get_settings] = lambda: Settings(admin_api_token=ADMIN_TOKEN)
    yield
    app.dependency_overrides.pop(get_settings, None)


def _seed_session(store, session_id: str, group: str) -> None:
    store.create_session(
        session_id=session_id,
        qr_id="QR-ENTRANCE-001",
        floor=1,
        x=3,
        y=50,
        store_id="meguro-dori",
        experiment_group=group,
    )
    store.insert_event(
        session_id=session_id, event_type="session_start", payload={}, experiment_group=group
    )


def _post_event(client, session_id: str, event_type: str, payload: dict | None = None):
    response = client.post(
        "/api/events",
        json={"session_id": session_id, "event_type": event_type, "payload": payload or {}},
    )
    assert response.status_code == 200, response.text
    return response


def _seed_two_group_events(client, store) -> None:
    """T1/T2/T3(treatment) と C1/C2(control) にファネルイベントを投入する。

    期待値（手計算・test_analyticsの計算と揃える）:
      treatment: scanned=3, related_viewed=2, related_tapped=1, route_viewed=2,
                 coordinate_viewed=1, chatbot_opened=1,
                 related_tap_rate=0.5, route_reach_rate=2/3, coordinate_view_rate=1/3,
                 sub_passage_rate=0.5
      control:   scanned=2, related_viewed=2, related_tapped=1, route_viewed=1,
                 coordinate_viewed=0, chatbot_opened=0,
                 related_tap_rate=0.5, route_reach_rate=0.5, coordinate_view_rate=0.0,
                 sub_passage_rate=1.0
    """
    _seed_session(store, "T1", TREATMENT)
    _seed_session(store, "T2", TREATMENT)
    _seed_session(store, "T3", TREATMENT)
    _seed_session(store, "C1", CONTROL)
    _seed_session(store, "C2", CONTROL)

    _post_event(client, "T1", "qr_scan")
    _post_event(client, "T1", "related_view")
    _post_event(client, "T1", "related_tap")
    _post_event(client, "T1", "route_view", {"via_sub_passage": True})
    _post_event(client, "T1", "coordinate_view")
    _post_event(client, "T1", "chatbot_open")

    _post_event(client, "T2", "qr_scan")
    _post_event(client, "T2", "related_view")
    _post_event(client, "T2", "route_view", {"via_sub_passage": False})

    _post_event(client, "T3", "qr_scan")

    _post_event(client, "C1", "qr_scan")
    _post_event(client, "C1", "related_view")
    _post_event(client, "C1", "related_tap")
    _post_event(client, "C1", "route_view", {"via_sub_passage": True})

    _post_event(client, "C2", "qr_scan")
    _post_event(client, "C2", "related_view")


def test_admin_kpi_requires_token_returns_401_without_header(client):
    response = client.get("/api/admin/kpi")

    assert response.status_code == 401
    assert response.json()["code"] == "ADMIN_UNAUTHORIZED"


def test_admin_kpi_requires_token_returns_401_with_wrong_token(client):
    response = client.get("/api/admin/kpi", headers={"X-Admin-Token": "wrong-token"})

    assert response.status_code == 401
    assert response.json()["code"] == "ADMIN_UNAUTHORIZED"


def test_admin_kpi_returns_group_funnel_rates_and_ab_diff(client, store):
    app.dependency_overrides[get_pos_metrics] = lambda: None
    try:
        _seed_two_group_events(client, store)

        response = client.get("/api/admin/kpi", headers={"X-Admin-Token": ADMIN_TOKEN})
    finally:
        app.dependency_overrides.pop(get_pos_metrics, None)

    assert response.status_code == 200
    body = response.json()

    treatment = body["groups"][TREATMENT]
    assert treatment["session_count"] == 3
    assert treatment["funnel"] == {
        "scanned": 3,
        "related_viewed": 2,
        "related_tapped": 1,
        "route_viewed": 2,
        "coordinate_viewed": 1,
        "chatbot_opened": 1,
    }
    assert treatment["rates"]["related_tap_rate"] == pytest.approx(0.5)
    assert treatment["rates"]["route_reach_rate"] == pytest.approx(2 / 3)
    assert treatment["rates"]["coordinate_view_rate"] == pytest.approx(1 / 3)
    assert treatment["rates"]["sub_passage_rate"] == pytest.approx(0.5)

    control = body["groups"][CONTROL]
    assert control["session_count"] == 2
    assert control["funnel"] == {
        "scanned": 2,
        "related_viewed": 2,
        "related_tapped": 1,
        "route_viewed": 1,
        "coordinate_viewed": 0,
        "chatbot_opened": 0,
    }
    assert control["rates"]["route_reach_rate"] == pytest.approx(0.5)
    assert control["rates"]["sub_passage_rate"] == pytest.approx(1.0)

    diff = body["diff"]
    assert diff["related_tap_rate"] == pytest.approx(0.0)
    assert diff["route_reach_rate"] == pytest.approx(2 / 3 - 0.5)
    assert diff["coordinate_view_rate"] == pytest.approx(1 / 3 - 0.0)
    assert diff["sub_passage_rate"] == pytest.approx(0.5 - 1.0)

    assert body["pos_metrics"] is None
    assert isinstance(body["note"], str) and body["note"]


def test_admin_kpi_pos_metrics_present_returns_values_and_diff(client, store):
    pos_metrics = {
        TREATMENT: {
            "co_purchase_rate": 0.3,
            "items_per_purchase": 2.5,
            "spend_per_customer": 6000,
        },
        CONTROL: {
            "co_purchase_rate": 0.2,
            "items_per_purchase": 2.0,
            "spend_per_customer": 5000,
        },
    }
    app.dependency_overrides[get_pos_metrics] = lambda: pos_metrics
    try:
        _seed_session(store, "T1", TREATMENT)
        _seed_session(store, "C1", CONTROL)

        response = client.get("/api/admin/kpi", headers={"X-Admin-Token": ADMIN_TOKEN})
    finally:
        app.dependency_overrides.pop(get_pos_metrics, None)

    assert response.status_code == 200
    pos = response.json()["pos_metrics"]
    assert pos["groups"][TREATMENT]["co_purchase_rate"] == pytest.approx(0.3)
    assert pos["groups"][CONTROL]["co_purchase_rate"] == pytest.approx(0.2)
    assert pos["diff"]["co_purchase_rate"] == pytest.approx(0.1)
    assert pos["diff"]["items_per_purchase"] == pytest.approx(0.5)
    assert pos["diff"]["spend_per_customer"] == pytest.approx(1000)


def test_admin_kpi_pos_metrics_absent_returns_null(client, store):
    app.dependency_overrides[get_pos_metrics] = lambda: None
    try:
        _seed_session(store, "T1", TREATMENT)

        response = client.get("/api/admin/kpi", headers={"X-Admin-Token": ADMIN_TOKEN})
    finally:
        app.dependency_overrides.pop(get_pos_metrics, None)

    assert response.status_code == 200
    assert response.json()["pos_metrics"] is None


def test_admin_kpi_default_pos_metrics_dependency_reads_sample_data_file(client, store):
    """`get_pos_metrics` を上書きしない場合、`data/pos_metrics.json`（サンプル値）を
    実際に読み込んで pos_metrics が値を持つことを確認する（本フェーズで追加したサンプル
    データが実際に配線されていることの回帰確認）。"""
    _seed_session(store, "T1", TREATMENT)

    response = client.get("/api/admin/kpi", headers={"X-Admin-Token": ADMIN_TOKEN})

    assert response.status_code == 200
    pos = response.json()["pos_metrics"]
    assert pos is not None
    assert pos["groups"][TREATMENT]["co_purchase_rate"] is not None
