"""リクエストボディの型定義（17章 API仕様）。

レスポンスは辞書をそのまま返す（内部の dataclass/リポジトリ結果を明示的に整形して
返却する方が実装意図が読みやすいため）。OpenAPI スキーマ上のレスポンス型記述は
後続ステップで `response_model` を精緻化する余地を残す（コメントで明記）。
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class LocationSignal(BaseModel):
    """来店判定用の任意の位置シグナル（フェーズ3-B）。緯度経度のみ・精密測位は行わない。"""

    lat: float
    lng: float


class CreateSessionRequest(BaseModel):
    """`POST /api/session` リクエストボディ。

    `location`/`wifi_ssid` はフェーズ3-B（Wi-Fi/ジオフェンスによる来店判定の高度化・
    DECISIONS.md #7）で追加した**任意**フィールド。既定の来店検証モード(`qr`)では
    無視され、指定してもしなくても挙動は変わらない（後方互換）。`VISIT_VERIFICATION_MODE`
    が `geofence`/`wifi` を含む場合のみ、来店ロック判定（`require_active_session`）で
    参照される。9章プライバシー: これらは来店判定にのみ使用し、`events`（効果ログ）には
    保存しない。
    """

    qr_id: str
    location: Optional[LocationSignal] = None
    wifi_ssid: Optional[str] = None


class EventRequest(BaseModel):
    """`POST /api/events` リクエストボディ。"""

    session_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
