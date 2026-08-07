"""`POST /api/session`（17章）: 来店セッション開始（QR起点を記録）。"""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..dependencies import get_qr_repo, get_store, get_experiment_assigner
from ..errors import ApiError
from ..experiment import ExperimentAssigner
from ..repositories import QrRepository
from ..schemas import CreateSessionRequest
from ..store import Store

router = APIRouter(tags=["session"])


@router.post("/api/session")
def create_session(
    body: CreateSessionRequest,
    qr_repo: QrRepository = Depends(get_qr_repo),
    store: Store = Depends(get_store),
    assigner: ExperimentAssigner = Depends(get_experiment_assigner),
    settings: Settings = Depends(get_settings),
) -> dict:
    qr = qr_repo.get(body.qr_id)
    if qr is None:
        # 不正な qr_id（19章 エッジケース: QR読取失敗・破損QR）
        raise ApiError(
            status_code=404,
            code="QR_NOT_FOUND",
            message=f"qr_id={body.qr_id} は登録されていません。",
        )

    session_id = str(uuid4())
    experiment_group = assigner.assign()

    # フェーズ3-B（来店判定の高度化）: location/wifi_ssid は任意の来店判定シグナル。
    # `sessions`（判定用）にのみ保持し、下記の `session_start` イベント（events＝効果ログ）
    # には一切含めない（9章プライバシー「ログはセッション単位で匿名」）。
    store.create_session(
        session_id=session_id,
        qr_id=qr["qr_id"],
        floor=qr["floor"],
        x=qr["x"],
        y=qr["y"],
        store_id=settings.store_id,
        experiment_group=experiment_group,
        location_lat=body.location.lat if body.location else None,
        location_lng=body.location.lng if body.location else None,
        wifi_ssid=body.wifi_ssid,
    )

    # 10章 計測・ログ設計: session_start（起点QRの種別・座標・店舗・実験群を記録）
    # 9章プライバシー: location/wifi_ssid はここに含めない（events未保存を徹底）。
    store.insert_event(
        session_id=session_id,
        event_type="session_start",
        payload={
            "qr_id": qr["qr_id"],
            "qr_type": qr["type"],
            "product_id": qr.get("product_id"),
            "floor": qr["floor"],
            "x": qr["x"],
            "y": qr["y"],
            "store_id": settings.store_id,
            "experiment_group": experiment_group,
        },
        experiment_group=experiment_group,
    )

    return {
        "session_id": session_id,
        "start": {"floor": qr["floor"], "x": qr["x"], "y": qr["y"]},
        "floor": qr["floor"],
        "experiment_group": experiment_group,
    }
