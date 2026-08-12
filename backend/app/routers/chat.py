"""`POST /api/chat/turn`: 商品文脈付きガイド型チャット。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..chat import ChatService
from ..dependencies import get_chat_service, get_store, require_active_session
from ..schemas import ChatTurnRequest
from ..store import Store

router = APIRouter(tags=["chat"])


@router.post("/api/chat/turn")
def post_chat_turn(
    body: ChatTurnRequest,
    session: dict[str, Any] = Depends(require_active_session),
    service: ChatService = Depends(get_chat_service),
    store: Store = Depends(get_store),
) -> dict[str, Any]:
    response = service.turn(body)

    # 自由入力本文は保存しない。質問・選択肢・提示商品という分析に必要な匿名信号だけを残す。
    event_type = "chatbot_open" if body.action == "start" else "chatbot_answer"
    if body.action == "finish":
        event_type = "chatbot_finish"
    store.insert_event(
        session_id=session["session_id"],
        event_type=event_type,
        payload={
            "product_id": body.product_id,
            "action": body.action,
            "question_id": body.question_id,
            "answer_id": body.answer_id,
            "used_free_text": bool(body.text),
            "mode": body.mode,
            "completed": response["completed"],
        },
        experiment_group=session["experiment_group"],
    )
    if response["completed"] and event_type != "chatbot_finish":
        # 3問完了時は最後の回答イベントに加えて完了イベントを残す。明示的な終了ボタンを
        # 押さなくても完了率を正しく計測できるようにするためである。
        store.insert_event(
            session_id=session["session_id"],
            event_type="chatbot_finish",
            payload={"product_id": body.product_id, "reason": "questions_completed"},
            experiment_group=session["experiment_group"],
        )
    if response["recommendations"]:
        store.insert_event(
            session_id=session["session_id"],
            event_type="chatbot_recommendation_view",
            payload={
                "product_id": body.product_id,
                "recommended_product_ids": [
                    item["product"].get("product_id") for item in response["recommendations"]
                ],
                "preference_keys": sorted(response["state"]["preferences"].keys()),
            },
            experiment_group=session["experiment_group"],
        )
    return response
