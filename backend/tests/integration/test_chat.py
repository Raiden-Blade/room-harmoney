"""商品文脈付きガイド型チャットAPIの結合テスト。"""
from __future__ import annotations

import pytest


def _start_payload(product_id: str = "P027") -> dict:
    return {
        "product_id": product_id,
        "action": "start",
        "mode": "customer",
        "state": {"answered_question_ids": [], "preferences": {}},
    }


def test_chat_requires_active_store_session(client) -> None:
    response = client.post("/api/chat/turn", json=_start_payload())

    assert response.status_code == 409
    assert response.json()["code"] == "VISIT_LOCK_REQUIRED"


def test_chat_start_returns_guided_question_and_existing_recommendations(
    client, active_session, store
) -> None:
    response = client.post(
        f"/api/chat/turn?session_id={active_session['session_id']}",
        json=_start_payload(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["question"]["question_id"] == "focus"
    assert 1 <= len(body["recommendations"]) <= 6
    assert body["state"] == {"answered_question_ids": [], "preferences": {}}
    assert body["route_product_ids"]
    assert "仮想値" in body["data_notice"]
    # 初期候補が同一カテゴリだけで埋まらず、関連する複数の商品種類を認知できること。
    assert len({item["cat_mid"] for item in body["recommendations"]}) >= 2

    events = store.list_events(active_session["session_id"])
    assert [event["event_type"] for event in events[-2:]] == [
        "chatbot_open",
        "chatbot_recommendation_view",
    ]


def test_chat_answer_updates_state_without_persisting_free_text(
    client, active_session, store
) -> None:
    payload = {
        "product_id": "P027",
        "action": "answer",
        "question_id": "focus",
        "text": "価格を抑えて見たいです",
        "mode": "customer",
        "state": {"answered_question_ids": [], "preferences": {}},
    }
    response = client.post(
        f"/api/chat/turn?session_id={active_session['session_id']}", json=payload
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recognized"] is True
    assert body["state"]["preferences"]["focus"] == "budget"
    assert body["state"]["answered_question_ids"] == ["focus"]

    event = next(
        event
        for event in store.list_events(active_session["session_id"])
        if event["event_type"] == "chatbot_answer"
    )
    assert event["payload"]["used_free_text"] is True
    assert "価格を抑えて" not in str(event["payload"])


def test_chat_rejects_answer_for_stale_question(client, active_session) -> None:
    payload = {
        "product_id": "P027",
        "action": "answer",
        "question_id": "route",
        "answer_id": "closest",
        "state": {"answered_question_ids": [], "preferences": {}},
    }
    response = client.post(
        f"/api/chat/turn?session_id={active_session['session_id']}", json=payload
    )

    assert response.status_code == 422
    assert response.json()["code"] == "CHAT_QUESTION_MISMATCH"


def test_chat_unknown_product_returns_same_api_error_contract(client, active_session) -> None:
    response = client.post(
        f"/api/chat/turn?session_id={active_session['session_id']}",
        json=_start_payload("UNKNOWN"),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"


def test_chat_staff_mode_adds_numeric_evidence(client, active_session) -> None:
    payload = _start_payload()
    payload["mode"] = "staff"
    response = client.post(
        f"/api/chat/turn?session_id={active_session['session_id']}", json=payload
    )

    assert response.status_code == 200
    reasons = response.json()["recommendations"][0]["reasons"]
    assert any(reason.startswith("併売リフト:") for reason in reasons)


def test_chat_completes_in_at_most_three_questions_and_logs_automatic_finish(
    client, active_session, store
) -> None:
    url = f"/api/chat/turn?session_id={active_session['session_id']}"
    response = client.post(url, json=_start_payload()).json()
    seen_questions: list[str] = []

    while response["question"] is not None:
        question = response["question"]
        seen_questions.append(question["question_id"])
        # 「おまかせ／未指定」に相当する選択肢があれば優先し、無ければ先頭を選ぶ。
        option_ids = [option["option_id"] for option in question["options"]]
        neutral = next(
            (
                option_id
                for option_id in option_ids
            if option_id in {"balanced", "no_preference", "relevance"}
            ),
            option_ids[0],
        )
        result = client.post(
            url,
            json={
                "product_id": "P027",
                "action": "answer",
                "question_id": question["question_id"],
                "answer_id": neutral,
                "mode": "customer",
                "state": response["state"],
            },
        )
        assert result.status_code == 200, result.text
        response = result.json()

    assert seen_questions == ["focus", "category", "color"]
    assert response["completed"] is True
    assert len(response["state"]["answered_question_ids"]) == 3
    assert any(
        event["event_type"] == "chatbot_finish"
        for event in store.list_events(active_session["session_id"])
    )


@pytest.mark.parametrize("focus", ["relevance", "discovery"])
def test_category_answer_moves_selected_category_to_top(
    client, active_session, focus: str
) -> None:
    url = f"/api/chat/turn?session_id={active_session['session_id']}"
    first = client.post(url, json=_start_payload()).json()
    second = client.post(
        url,
        json={
            "product_id": "P027",
            "action": "answer",
            "question_id": "focus",
            "answer_id": focus,
            "state": first["state"],
        },
    ).json()
    selected_option = next(
        option
        for option in second["question"]["options"]
        if option["option_id"].startswith("category:")
    )
    selected_category = selected_option["option_id"].split(":", 1)[1]

    result = client.post(
        url,
        json={
            "product_id": "P027",
            "action": "answer",
            "question_id": "category",
            "answer_id": selected_option["option_id"],
            "state": second["state"],
        },
    )

    assert result.status_code == 200, result.text
    assert result.json()["recommendations"][0]["cat_mid"] == selected_category
