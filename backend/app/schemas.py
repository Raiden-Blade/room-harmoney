"""リクエストボディの型定義（17章 API仕様）。

レスポンスは辞書をそのまま返す（内部の dataclass/リポジトリ結果を明示的に整形して
返却する方が実装意図が読みやすいため）。OpenAPI スキーマ上のレスポンス型記述は
後続ステップで `response_model` を精緻化する余地を残す（コメントで明記）。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """`POST /api/session` リクエストボディ。"""

    qr_id: str


class EventRequest(BaseModel):
    """`POST /api/events` リクエストボディ。"""

    session_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
