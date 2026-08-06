"""`POST /api/events`（17章・10章）: 効果ログ記録。

`event_type` は10章（計測・ログ設計）で列挙されたイベント種別の許可リストで検証する。
`session_id` から `experiment_group` を引いて必ず events に付与する（AC-4）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_store
from ..errors import ApiError
from ..schemas import EventRequest
from ..store import Store

router = APIRouter(tags=["events"])

# 10章「計測・ログ設計」に列挙されたイベント種別（DESIGN.md events.event_type の enum も同じ）。
ALLOWED_EVENT_TYPES = {
    "session_start",
    "qr_scan",
    "related_view",
    "related_tap",
    "coordinate_view",
    "coordinate_tap",
    "route_view",
    "chatbot_open",
    "experiment_group",
}


@router.post("/api/events")
def post_event(body: EventRequest, store: Store = Depends(get_store)) -> dict:
    if body.event_type not in ALLOWED_EVENT_TYPES:
        raise ApiError(
            status_code=422,
            code="INVALID_EVENT_TYPE",
            message=f"event_type={body.event_type} は許可されていません。"
            f"許可値: {sorted(ALLOWED_EVENT_TYPES)}",
        )

    session = store.get_session(body.session_id)
    if session is None:
        raise ApiError(
            status_code=404,
            code="SESSION_NOT_FOUND",
            message=f"session_id={body.session_id} が見つかりません。",
        )

    event = store.insert_event(
        session_id=body.session_id,
        event_type=body.event_type,
        payload=body.payload,
        experiment_group=session["experiment_group"],
    )
    return event
