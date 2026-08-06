"""`GET /api/qr/{qr_id}`（17章）: QR解決（入口/商品の判別）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_qr_repo
from ..errors import ApiError
from ..repositories import QrRepository

router = APIRouter(tags=["qr"])


@router.get("/api/qr/{qr_id}")
def resolve_qr(qr_id: str, qr_repo: QrRepository = Depends(get_qr_repo)) -> dict:
    qr = qr_repo.get(qr_id)
    if qr is None:
        raise ApiError(
            status_code=404,
            code="QR_NOT_FOUND",
            message=f"qr_id={qr_id} は登録されていません。",
        )
    return {
        "type": qr["type"],
        "product_id": qr.get("product_id"),
        "position": {"floor": qr["floor"], "x": qr["x"], "y": qr["y"]},
        "direct_url": qr["direct_url"],
    }
