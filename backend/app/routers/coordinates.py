"""`GET /api/coordinates/{coordinate_id}`（17章）: コーディネート詳細。

`session_id` は任意（付与されればイベント記録に使う。参照系のみのため来店ロックは
かけない設計。関連表示・ルートのみを来店ロック対象とする方針は
「G2 API結合」実装指示に基づく前提として明記する）。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_coordinate_repo, get_product_repo, get_store
from ..errors import ApiError
from ..repositories import CoordinateRepository, ProductRepository
from ..store import Store

router = APIRouter(tags=["coordinates"])


@router.get("/api/coordinates/{coordinate_id}")
def get_coordinate(
    coordinate_id: str,
    session_id: Optional[str] = Query(default=None),
    coordinate_repo: CoordinateRepository = Depends(get_coordinate_repo),
    product_repo: ProductRepository = Depends(get_product_repo),
    store: Store = Depends(get_store),
) -> dict:
    coordinate = coordinate_repo.get(coordinate_id)
    if coordinate is None:
        raise ApiError(
            status_code=404,
            code="COORDINATE_NOT_FOUND",
            message=f"coordinate_id={coordinate_id} は見つかりません。",
        )

    products = [
        product_repo.get(pid) for pid in coordinate.get("product_ids", [])
    ]
    products = [p for p in products if p is not None]

    if session_id:
        session = store.get_session(session_id)
        if session is not None:
            # 10章 計測: coordinate_view。無効な session_id はサイレントに無視する
            # （コーデ閲覧自体は来店ロック対象外のため、ログ付与の失敗でユーザー体験を止めない）。
            store.insert_event(
                session_id=session_id,
                event_type="coordinate_view",
                payload={"coordinate_id": coordinate_id},
                experiment_group=session["experiment_group"],
            )

    return {**coordinate, "products": products}
