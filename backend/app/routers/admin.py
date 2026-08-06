"""`GET /api/admin/kpi`（17章「管理系は認証必須」／10章 計測・ログ設計／12章 KPI）。

experiment_group（treatment/control）別にイベントログを集計し、ファネル・率・A/B差分・
（あれば）POS突合スロットを返す管理系エンドポイント。集計ロジック本体は `app/analytics.py`
の純粋関数 `compute_kpis` に切り出し、本ルータは「認証→データ取得→集計呼び出し」の結線
のみを担う（責務分離）。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends

from ..analytics import compute_kpis
from ..dependencies import get_pos_metrics, get_store, require_admin
from ..store import Store

router = APIRouter(tags=["admin"])


@router.get("/api/admin/kpi", dependencies=[Depends(require_admin)])
def get_admin_kpi(
    store: Store = Depends(get_store),
    pos_metrics: Optional[dict[str, Any]] = Depends(get_pos_metrics),
) -> dict:
    events = store.list_events()
    return compute_kpis(events, pos_metrics=pos_metrics)
