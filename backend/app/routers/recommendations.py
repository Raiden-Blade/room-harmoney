"""`GET /api/recommendations`（17章）: 関連商品＋コーディネート（B1 HybridRecommender 結線）。

来店ロック（9章・AC-5）: 有効な session_id が無い/失効していれば `require_active_session`
が 409 を送出し、この関数本体には到達しない。

フェーズ3-A（DECISIONS.md 改訂#5-A）: 任意クエリ `member_id` を追加。指定があれば
`PersonalizedRecommender`（`get_recommender` の実体）が会員購入履歴でパーソナライズし、
未指定なら従来どおり（base推薦と完全一致）。**プライバシー厳守**（9章）: `member_id` は
`events`（効果ログ）には一切保存しない。ログ・レスポンスには `personalized`（真偽値）
のみを残し、会員IDそのものを含めない。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from recommender import RecommenderInterface

from ..dependencies import get_recommender, get_store, require_active_session
from ..errors import ApiError
from ..store import Store

router = APIRouter(tags=["recommendations"])


@router.get("/api/recommendations")
def get_recommendations(
    product_id: str,
    member_id: Optional[str] = Query(
        default=None,
        description=(
            "会員ID（任意・フェーズ3-A個人最適化）。未指定/不明会員/購入履歴が空の場合は"
            "従来どおりベース推薦と完全に同一の結果を返す（DECISIONS.md 改訂#5-A）。"
        ),
    ),
    session: dict[str, Any] = Depends(require_active_session),
    recommender: RecommenderInterface = Depends(get_recommender),
    store: Store = Depends(get_store),
) -> dict:
    result = recommender.recommend(product_id, member_id=member_id)
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
    # 9章プライバシー: member_id 自体は保存しない。個人最適化が適用されたリクエストか
    # どうかの真偽値（personalized）のみを残す（会員を特定できる情報は含めない）。
    store.insert_event(
        session_id=session["session_id"],
        event_type="related_view",
        payload={
            "product_id": product_id,
            "related_product_ids": [item.product.get("product_id") for item in result.related],
            "coordinate_ids": [c.get("coordinate_id") for c in result.coordinates],
            "personalized": member_id is not None,
        },
        experiment_group=session["experiment_group"],
    )

    return {
        "related": related_payload,
        "coordinates": result.coordinates,
        "personalized": member_id is not None,
    }
