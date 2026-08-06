"""`GET /api/recommendations`（17章）: 関連商品＋コーディネート（B1 HybridRecommender 結線）。

来店ロック（9章・AC-5）: 有効な session_id が無い/失効していれば `require_active_session`
が 409 を送出し、この関数本体には到達しない。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from recommender import RecommenderInterface

from ..dependencies import get_recommender, get_store, require_active_session
from ..errors import ApiError
from ..store import Store

router = APIRouter(tags=["recommendations"])


@router.get("/api/recommendations")
def get_recommendations(
    product_id: str,
    session: dict[str, Any] = Depends(require_active_session),
    recommender: RecommenderInterface = Depends(get_recommender),
    store: Store = Depends(get_store),
) -> dict:
    result = recommender.recommend(product_id)
    if not result.product_found:
        raise ApiError(
            status_code=404,
            code="PRODUCT_NOT_FOUND",
            message=f"product_id={product_id} は見つかりません。",
        )

    related_payload = [
        {
            "product": item.product,
            "cat_mid": item.cat_mid,
            "lift": item.lift,
            "high_lift_low_corate": item.high_lift_low_corate,
            "score": item.score,
        }
        for item in result.related
    ]

    # 10章 計測: related_view（表示された関連商品）。experiment_group はセッションから付与。
    store.insert_event(
        session_id=session["session_id"],
        event_type="related_view",
        payload={
            "product_id": product_id,
            "related_product_ids": [item.product.get("product_id") for item in result.related],
            "coordinate_ids": [c.get("coordinate_id") for c in result.coordinates],
        },
        experiment_group=session["experiment_group"],
    )

    return {"related": related_payload, "coordinates": result.coordinates}
