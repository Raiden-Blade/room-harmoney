"""`POST /api/events`（17章・10章）の結合テスト。"""
from __future__ import annotations


def test_post_allowed_event_type_is_recorded_with_experiment_group(client, active_session, store):
    response = client.post(
        "/api/events",
        json={
            "session_id": active_session["session_id"],
            "event_type": "chatbot_open",
            "payload": {"source": "s2_product_detail"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["event_type"] == "chatbot_open"
    assert body["session_id"] == active_session["session_id"]
    # AC-4: session_id から引いた experiment_group が必ず付与される。
    assert body["experiment_group"] == active_session["experiment_group"]

    events = store.list_events(session_id=active_session["session_id"])
    chatbot_events = [e for e in events if e["event_type"] == "chatbot_open"]
    assert len(chatbot_events) == 1
    assert chatbot_events[0]["payload"] == {"source": "s2_product_detail"}
    assert chatbot_events[0]["experiment_group"] == active_session["experiment_group"]


def test_post_event_without_client_supplied_experiment_group_still_gets_one(
    client, active_session
):
    """クライアントが experiment_group をpayloadに含めなくても、サーバ側でセッションから
    必ず付与される（AC-4: 個人情報等をURLに載せない設計とも整合し、experiment_groupは
    セッションに紐づく形でサーバが管理する）。
    """
    response = client.post(
        "/api/events",
        json={
            "session_id": active_session["session_id"],
            "event_type": "related_tap",
            "payload": {"product_id": "P002"},
        },
    )

    assert response.status_code == 200
    assert response.json()["experiment_group"] is not None
    assert response.json()["experiment_group"] == active_session["experiment_group"]


def test_post_event_with_disallowed_event_type_returns_422(client, active_session):
    response = client.post(
        "/api/events",
        json={
            "session_id": active_session["session_id"],
            "event_type": "not_a_real_event_type",
            "payload": {},
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_EVENT_TYPE"


def test_post_event_with_unknown_session_id_returns_404(client):
    response = client.post(
        "/api/events",
        json={"session_id": "not-a-real-session", "event_type": "chatbot_open", "payload": {}},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "SESSION_NOT_FOUND"


def test_post_event_missing_required_field_returns_422(client, active_session):
    """`event_type` 欠如などスキーマ違反は Pydantic による標準422になる。"""
    response = client.post(
        "/api/events",
        json={"session_id": active_session["session_id"], "payload": {}},
    )

    assert response.status_code == 422
