"""`GET /api/recommendations`（17章）: 関連商品＋コーディネート（B1 HybridRecommender 結線）。

来店ロック（9章・AC-5）: 有効な session_id が無い/失効していれば `require_active_session`
が 409 を送出し、この関数本体には到達しない。

フェーズ3-A（DECISIONS.md 改訂#5-A）: 任意クエリ `member_id` を追加。指定があれば
`PersonalizedRecommender`（`get_recommender` の実体）が会員購入履歴でパーソナライズし、
未指定なら従来どおり（base推薦と完全一致）。**プライバシー厳守**（9章）: `member_id` は
`events`（効果ログ）には一切保存しない。ログ・レスポンスには `personalized`（真偽値）
のみを残し、会員IDそのものを含めない。

段階B2（実商品データ9,180件への差し替え）: 任意クエリ `limit`（既定12）を追加。実データでは
1中分類に1,000件超の商品が属することがあり、related を無制限に返すとレスポンスが肥大化する
（性能・UI双方の観点）。`RecommenderInterface` のコア実装（`recommender/hybrid.py`・
`recommender/personalized.py`）は変更せず、全件をスコア降順で算出させたうえで**API層で
上位 `limit` 件にスライス**する（推薦ロジックと配信件数制御の責務分離）。`coordinates` は
対象外（起点商品を含むコーデのみを返す既存仕様のため、通常は少数件で収まる）。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from recommender import RecommenderInterface

from ..dependencies import get_recommender, get_store, require_active_session
from ..errors import ApiError
from ..store import Store

router = APIRouter(tags=["recommendations"])

DEFAULT_RELATED_LIMIT = 12


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
    limit: int = Query(
        default=DEFAULT_RELATED_LIMIT,
        ge=1,
        description=(
            "関連商品（related）の最大件数（段階B2・既定12）。スコア降順で上位 limit 件のみ返す。"
            "coordinates には適用しない。"
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

    limited_related = result.related[:limit]

    related_payload = [
        {
            "product": item.product,
            "cat_mid": item.cat_mid,
            "lift": item.lift,
            "high_lift_low_corate": item.high_lift_low_corate,
            "score": item.score,
        }
        for item in limited_related
    ]

    # 10章 計測: related_view（表示された関連商品）。experiment_group はセッションから付与。
    # 9章プライバシー: member_id 自体は保存しない。個人最適化が適用されたリクエストか
    # どうかの真偽値（personalized）のみを残す（会員を特定できる情報は含めない）。
    store.insert_event(
        session_id=session["session_id"],
        event_type="related_view",
        payload={
            "product_id": product_id,
            "related_product_ids": [item.product.get("product_id") for item in limited_related],
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
