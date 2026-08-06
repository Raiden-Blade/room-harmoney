"""`GET /api/route`（17章）の結合テスト。B2 RouteGraphBuilder 結線・来店ロック・計測を検証する。"""
from __future__ import annotations

import pytest

from app.dependencies import get_route_builder
from app.main import app
from routing import RouteGraphBuilder


def test_route_without_session_returns_409(client):
    """AC-5: 来店ロック。"""
    response = client.get(
        "/api/route", params={"from_qr": "QR-ENTRANCE-001", "to_product": "P001"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "VISIT_LOCK_REQUIRED"


def test_route_single_destination_returns_waypoint_list(client, active_session):
    response = client.get(
        "/api/route",
        params={
            "from_qr": "QR-ENTRANCE-001",
            "to_product": "P001",
            "session_id": active_session["session_id"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {"waypoints", "sub_passages", "visiting_order"}
    assert body["visiting_order"] == ["P001"]
    assert len(body["waypoints"]) >= 2
    # 起点は入口QRの座標と一致する。
    assert body["waypoints"][0]["floor"] == 1
    assert body["waypoints"][0]["x"] == pytest.approx(3)
    assert body["waypoints"][0]["y"] == pytest.approx(50)
    # 目的地は商品P001の座標に一致する。
    assert body["waypoints"][-1]["x"] == pytest.approx(17)
    assert body["waypoints"][-1]["y"] == pytest.approx(18)
    # P001 の最短経路はサブ通路を経由しない。
    assert body["sub_passages"] == []


def test_route_destination_via_sub_passage_reports_sub_passage_waypoint(client, active_session):
    """P009 は sub_passage_flag=true の商品で、経路はサブ通路ウェイポイントを経由する（AC-3）。"""
    response = client.get(
        "/api/route",
        params={
            "from_qr": "QR-ENTRANCE-001",
            "to_product": "P009",
            "session_id": active_session["session_id"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["visiting_order"] == ["P009"]
    assert len(body["sub_passages"]) >= 1


def test_route_multi_destination_returns_nearest_neighbor_visiting_order(client, active_session):
    """複数目的地の巡回順（B2 最近傍法）: 入口から近いP001が先、遠いP009が後。"""
    response = client.get(
        "/api/route",
        params={
            "from_qr": "QR-ENTRANCE-001",
            "to_product": ["P001", "P009"],
            "session_id": active_session["session_id"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["visiting_order"] == ["P001", "P009"]
    assert len(body["sub_passages"]) >= 1
    assert body["unreachable"] == []


def test_route_unknown_from_qr_returns_404(client, active_session):
    response = client.get(
        "/api/route",
        params={
            "from_qr": "QR-DOES-NOT-EXIST",
            "to_product": "P001",
            "session_id": active_session["session_id"],
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "QR_NOT_FOUND"


def test_route_unknown_to_product_returns_404(client, active_session):
    response = client.get(
        "/api/route",
        params={
            "from_qr": "QR-ENTRANCE-001",
            "to_product": "DOES-NOT-EXIST",
            "session_id": active_session["session_id"],
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"


def test_route_product_without_reachable_node_returns_404_route_not_found(client, active_session):
    """19章 エッジケース: 商品座標に対応する経路ノードがグラフ上に1つも無い場合は
    `route.py`（L64-74）が `RouteNotFoundError` を捕捉し 404 + code=ROUTE_NOT_FOUND を返す。

    QA G3レポートの提案（G2 QA提案）に基づく回帰テスト。ハリボテのモックにしないため、
    `route.py` 自体は変更せず、`get_route_builder` 依存だけを実物の `RouteGraphBuilder`
    （ただし「入口ノードは持つが商品近傍ノードを1つも持たない」店舗マップ）に差し替え、
    `RouteGraphBuilder.nearest_node` が実際に `RouteNotFoundError` を送出する経路を通す。
    """
    # QR-ENTRANCE-001 の起点座標（floor=1, x=3, y=50。他テストのassertと同じ実データ）には
    # 対応するノードを1つ用意するが、"商品近傍" タイプのノードは意図的に1つも含めない。
    unreachable_builder = RouteGraphBuilder(
        floors=[
            {
                "floor": 1,
                "waypoints": [
                    {"id": "entrance-only", "floor": 1, "x": 3, "y": 50, "type": "入口"},
                ],
                "edges": [],
            }
        ],
        inter_floor_edges=[],
    )
    app.dependency_overrides[get_route_builder] = lambda: unreachable_builder
    try:
        response = client.get(
            "/api/route",
            params={
                "from_qr": "QR-ENTRANCE-001",
                "to_product": "P001",
                "session_id": active_session["session_id"],
            },
        )
    finally:
        del app.dependency_overrides[get_route_builder]

    assert response.status_code == 404
    assert response.json()["code"] == "ROUTE_NOT_FOUND"


def test_route_records_route_view_event_with_experiment_group(client, active_session, store):
    response = client.get(
        "/api/route",
        params={
            "from_qr": "QR-ENTRANCE-001",
            "to_product": "P001",
            "session_id": active_session["session_id"],
        },
    )
    assert response.status_code == 200

    events = store.list_events(session_id=active_session["session_id"])
    route_view_events = [e for e in events if e["event_type"] == "route_view"]

    assert len(route_view_events) == 1
    event = route_view_events[0]
    assert event["experiment_group"] == active_session["experiment_group"]
    assert event["payload"]["from_qr"] == "QR-ENTRANCE-001"
    assert event["payload"]["visiting_order"] == ["P001"]
    # phase2-B1 追補: サブ通路通過率算出のため via_sub_passage を必ず含める。
    # P001 の最短経路はサブ通路を経由しないため false。
    assert event["payload"]["via_sub_passage"] is False


def test_route_records_via_sub_passage_true_when_route_passes_sub_passage(
    client, active_session, store
):
    """P009 はサブ通路経由（AC-3）。route_view payload の via_sub_passage が true になる
    ことを検証する（KPI集計のサブ通路通過率で使用）。"""
    response = client.get(
        "/api/route",
        params={
            "from_qr": "QR-ENTRANCE-001",
            "to_product": "P009",
            "session_id": active_session["session_id"],
        },
    )
    assert response.status_code == 200

    events = store.list_events(session_id=active_session["session_id"])
    route_view_events = [e for e in events if e["event_type"] == "route_view"]

    assert len(route_view_events) == 1
    assert route_view_events[0]["payload"]["via_sub_passage"] is True
