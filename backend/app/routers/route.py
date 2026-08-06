"""`GET /api/route`（17章）: 簡易ルート（B2 RouteGraphBuilder 結線）。

来店ロック（9章・AC-5）は `require_active_session` に委譲する。
複数 `to_product` を受け取り、`RouteGraphBuilder.multi_destination_route` の
最近傍法巡回順をそのまま配信する（並び順の正しさは G1 単体テストで担保済み）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from routing import RouteGraphBuilder, RouteNotFoundError

from ..dependencies import (
    get_product_repo,
    get_qr_repo,
    get_route_builder,
    get_store,
    require_active_session,
)
from ..errors import ApiError
from ..repositories import ProductRepository, QrRepository
from ..store import Store

router = APIRouter(tags=["route"])


@router.get("/api/route")
def get_route(
    from_qr: str,
    to_product: list[str] = Query(..., description="目的商品ID（複数指定可）"),
    session: dict[str, Any] = Depends(require_active_session),
    qr_repo: QrRepository = Depends(get_qr_repo),
    product_repo: ProductRepository = Depends(get_product_repo),
    route_builder: RouteGraphBuilder = Depends(get_route_builder),
    store: Store = Depends(get_store),
) -> dict:
    qr = qr_repo.get(from_qr)
    if qr is None:
        raise ApiError(
            status_code=404, code="QR_NOT_FOUND", message=f"qr_id={from_qr} は登録されていません。"
        )

    try:
        start_id = route_builder.nearest_node(floor=qr["floor"], x=qr["x"], y=qr["y"])
    except RouteNotFoundError as exc:
        raise ApiError(
            status_code=404,
            code="ROUTE_NOT_FOUND",
            message=f"起点QR（floor={qr['floor']}）に対応する経路ノードが見つかりません。",
        ) from exc

    destination_ids: list[str] = []
    node_id_to_product_id: dict[str, str] = {}
    for product_id in to_product:
        product = product_repo.get(product_id)
        if product is None:
            raise ApiError(
                status_code=404,
                code="PRODUCT_NOT_FOUND",
                message=f"product_id={product_id} は見つかりません。",
            )
        try:
            node_id = route_builder.nearest_node(
                floor=product["floor"], x=product["x"], y=product["y"], node_type="商品近傍"
            )
        except RouteNotFoundError as exc:
            # 19章 エッジケース: 対象商品が別フロア等で経路ノードに対応付けられない
            raise ApiError(
                status_code=404,
                code="ROUTE_NOT_FOUND",
                message=f"product_id={product_id} への経路ノードが見つかりません。",
            ) from exc
        destination_ids.append(node_id)
        node_id_to_product_id[node_id] = product_id

    multi_result = route_builder.multi_destination_route(start_id, destination_ids)

    if not multi_result.order:
        # 19章 エッジケース: 経路が見つからない（すべての目的地が到達不能）
        raise ApiError(
            status_code=404,
            code="ROUTE_NOT_FOUND",
            message="起点から到達可能な経路が見つかりませんでした。",
        )

    waypoints = [
        {"floor": w.floor, "x": w.x, "y": w.y, "type": w.type}
        for w in multi_result.all_waypoints
    ]
    sub_passages = [
        {"floor": w.floor, "x": w.x, "y": w.y}
        for w in multi_result.all_waypoints
        if w.type == "サブ通路"
    ]
    visiting_order = [node_id_to_product_id[node_id] for node_id in multi_result.order]
    unreachable_product_ids = [
        node_id_to_product_id[node_id] for node_id in multi_result.unreachable
    ]

    # 10章 計測: route_view（起点・目的地・経由サブ通路）
    # `via_sub_passage`（bool）は phase2-B1 の追補: analytics.compute_kpis の
    # 「サブ通路通過率」算出に必要なため、経路が1つでもサブ通路ウェイポイントを
    # 経由していれば true にする（sub_passages は既存フィールドのまま維持し後方互換）。
    store.insert_event(
        session_id=session["session_id"],
        event_type="route_view",
        payload={
            "from_qr": from_qr,
            "to_product": to_product,
            "visiting_order": visiting_order,
            "sub_passage_count": len(sub_passages),
            "via_sub_passage": bool(sub_passages),
            "unreachable": unreachable_product_ids,
        },
        experiment_group=session["experiment_group"],
    )

    return {
        "waypoints": waypoints,
        "sub_passages": sub_passages,
        "visiting_order": visiting_order,
        "unreachable": unreachable_product_ids,
        "total_distance": multi_result.total_distance,
    }
