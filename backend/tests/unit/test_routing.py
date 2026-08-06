"""経路計算（B2 RouteGraphBuilder）の単体テスト。18.1 / DESIGN.md B2 → G1 単体ゲート。

重点観点（実装指示より）:
  (1) 既知の小グラフで最短経路が正しい
  (2) 複数目的地の巡回順
  (3) 別フロアが階段/EV経由で解ける
  (4) 経路なしのハンドリング
  (5) サブ通路を含む経路
"""
import pytest

from routing import RouteGraphBuilder, RouteNotFoundError


def _small_two_floor_map() -> dict:
    """テスト用の小さな2フロア・グラフ（データ注入で検証容易性を確保）。"""
    floors = [
        {
            "floor": 1,
            "waypoints": [
                {"id": "f1_a", "floor": 1, "x": 0, "y": 0, "type": "通路"},
                {"id": "f1_b", "floor": 1, "x": 10, "y": 0, "type": "通路"},
                {"id": "f1_c", "floor": 1, "x": 20, "y": 0, "type": "通路"},
                {"id": "f1_sub", "floor": 1, "x": 25, "y": 0, "type": "サブ通路"},
                {"id": "f1_prod_x", "floor": 1, "x": 30, "y": 0, "type": "商品近傍"},
                {"id": "f1_stairs", "floor": 1, "x": 5, "y": 5, "type": "階段"},
                {"id": "f1_isolated", "floor": 1, "x": 99, "y": 99, "type": "商品近傍"},
            ],
            "edges": [
                {"from": "f1_a", "to": "f1_b", "distance": 10},
                {"from": "f1_b", "to": "f1_c", "distance": 10},
                {"from": "f1_c", "to": "f1_sub", "distance": 5},
                {"from": "f1_sub", "to": "f1_prod_x", "distance": 10},
                {"from": "f1_a", "to": "f1_stairs", "distance": 7},
                # 迂回になるが直結もしている「わざと長い」ダミー経路（最短経路選択の正しさを検証するため）
                {"from": "f1_a", "to": "f1_prod_x", "distance": 100},
            ],
        },
        {
            "floor": 2,
            "waypoints": [
                {"id": "f2_stairs", "floor": 2, "x": 5, "y": 5, "type": "階段"},
                {"id": "f2_a", "floor": 2, "x": 0, "y": 0, "type": "通路"},
                {"id": "f2_prod_y", "floor": 2, "x": 10, "y": 0, "type": "商品近傍"},
            ],
            "edges": [
                {"from": "f2_stairs", "to": "f2_a", "distance": 5},
                {"from": "f2_a", "to": "f2_prod_y", "distance": 10},
            ],
        },
    ]
    inter_floor_edges = [{"from": "f1_stairs", "to": "f2_stairs", "distance": 15}]
    return {"floors": floors, "inter_floor_edges": inter_floor_edges}


@pytest.fixture
def builder() -> RouteGraphBuilder:
    return RouteGraphBuilder.from_store_map(_small_two_floor_map())


def test_shortest_path_picks_the_actual_shortest_route(builder: RouteGraphBuilder):
    """(1) 既知の小グラフで最短経路が正しい（遠回りのダミー直結エッジより短い経路を選ぶ）。"""
    result = builder.shortest_path("f1_a", "f1_prod_x")

    assert result.node_ids == ["f1_a", "f1_b", "f1_c", "f1_sub", "f1_prod_x"]
    assert result.total_distance == pytest.approx(35.0)  # 10+10+5+10、直結100エッジは選ばれない
    assert result.floors == [1]


def test_same_start_and_end_returns_zero_distance_single_point(builder: RouteGraphBuilder):
    """エッジケース: 起点=目的地の場合は距離0・単一ノードを返す。"""
    result = builder.shortest_path("f1_a", "f1_a")

    assert result.node_ids == ["f1_a"]
    assert result.total_distance == 0.0


def test_multi_destination_route_proposes_nearest_neighbor_order(builder: RouteGraphBuilder):
    """(2) 複数目的地（コーデ構成品）の巡回順は最近傍法で近い方から提案される。"""
    # 入力順はあえて [prod_x, sub] とするが、f1_a から近いのは sub(25) の方が prod_x(35) より近い。
    result = builder.multi_destination_route("f1_a", ["f1_prod_x", "f1_sub"])

    assert result.order == ["f1_sub", "f1_prod_x"]
    assert result.total_distance == pytest.approx(25.0 + 10.0)  # a->sub(25) + sub->prod_x(10、直結エッジ)
    assert result.unreachable == []


def test_different_floor_is_solved_via_stairs_connection(builder: RouteGraphBuilder):
    """(3) 別フロアへの経路が階段（フロア間接続）経由で解ける。"""
    result = builder.shortest_path("f1_a", "f2_prod_y")

    assert result.floors == [1, 2]
    assert result.is_multi_floor is True
    assert "f1_stairs" in result.node_ids
    assert "f2_stairs" in result.node_ids
    # a->stairs(7) + stairs間(15) + f2_stairs->f2_a(5) + f2_a->f2_prod_y(10)
    assert result.total_distance == pytest.approx(37.0)


def test_no_route_raises_route_not_found_error(builder: RouteGraphBuilder):
    """(4) 到達不能なノード（孤立ノード）への経路はエラーとしてハンドリングできる。"""
    with pytest.raises(RouteNotFoundError):
        builder.shortest_path("f1_a", "f1_isolated")


def test_unknown_node_id_raises_route_not_found_error(builder: RouteGraphBuilder):
    """(4) 未知のウェイポイントIDもエラーとして安全にハンドリングできる。"""
    with pytest.raises(RouteNotFoundError):
        builder.shortest_path("f1_a", "NO-SUCH-NODE")


def test_multi_destination_route_reports_unreachable_destinations(builder: RouteGraphBuilder):
    """(4) 巡回順の一部が到達不能でも例外にせず unreachable として報告する。"""
    result = builder.multi_destination_route("f1_a", ["f1_prod_x", "f1_isolated"])

    assert result.order == ["f1_prod_x"]
    assert result.unreachable == ["f1_isolated"]


def test_route_can_include_sub_passage_waypoint(builder: RouteGraphBuilder):
    """(5) サブ通路ウェイポイントを経由/目的地とする経路を表現できる。"""
    result = builder.shortest_path("f1_a", "f1_sub")

    assert result.node_ids[-1] == "f1_sub"
    sub_points = result.sub_passage_waypoints
    assert len(sub_points) == 1
    assert sub_points[0].type == "サブ通路"


def test_nearest_node_resolves_qr_or_product_coordinate_to_waypoint(builder: RouteGraphBuilder):
    """from_qr/to_product 解決用: 座標から最寄りウェイポイントIDを引ける。"""
    nearest = builder.nearest_node(floor=1, x=32, y=1, node_type="商品近傍")
    assert nearest == "f1_prod_x"


def test_nearest_node_raises_when_no_candidate_on_floor(builder: RouteGraphBuilder):
    with pytest.raises(RouteNotFoundError):
        builder.nearest_node(floor=3, x=0, y=0)
