"""`GET /api/store-map/{floor}`（17章）: フロアマップ（フロアプラン・ゾーン・ウェイポイント）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_store_map_repo
from ..errors import ApiError
from ..repositories import StoreMapRepository

router = APIRouter(tags=["store-map"])


@router.get("/api/store-map/{floor}")
def get_store_map(
    floor: int, store_map_repo: StoreMapRepository = Depends(get_store_map_repo)
) -> dict:
    floor_data = store_map_repo.get_floor(floor)
    if floor_data is None:
        raise ApiError(
            status_code=404,
            code="FLOOR_NOT_FOUND",
            message=f"floor={floor} は対象フロアの範囲外です。",
        )
    return floor_data
