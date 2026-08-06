"""ウェイポイント・グラフの最短経路／複数目的地の巡回順（4.3章 / DESIGN.md B2）。

`store_map.json`（floors[].waypoints/edges + inter_floor_edges）から networkx グラフを構築し、
- `from_qr`（起点QRの最寄りウェイポイント）→ `to_product`（商品最寄りウェイポイント）の最短経路
- 複数目的地（コーディネート構成品）の巡回順
を計算する。テスト容易性のため、コンストラクタは floors/inter_floor_edges を直接受け取れる
（データ注入）ほか、`from_store_map()` / `from_store_map_file()` で data/ の実データからも構築可能。
"""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

import networkx as nx


class RouteNotFoundError(Exception):
    """経路が見つからない場合（未知ノード／到達不能な別成分）に送出する。"""


@dataclass
class RoutePoint:
    """経路上の1ウェイポイント（座標列描画用）。"""

    id: str
    floor: int
    x: float
    y: float
    type: str


@dataclass
class RouteResult:
    """単一目的地への最短経路。"""

    waypoints: list[RoutePoint] = field(default_factory=list)
    total_distance: float = 0.0
    floors: list[int] = field(default_factory=list)

    @property
    def node_ids(self) -> list[str]:
        return [w.id for w in self.waypoints]

    @property
    def is_multi_floor(self) -> bool:
        return len(self.floors) > 1

    @property
    def sub_passage_waypoints(self) -> list[RoutePoint]:
        """経路に含まれるサブ通路ウェイポイント（通過率を上げたい経由点）。"""
        return [w for w in self.waypoints if w.type == "サブ通路"]


@dataclass
class MultiRouteResult:
    """複数目的地（コーディネート構成品等）の巡回順の提案。"""

    order: list[str] = field(default_factory=list)
    legs: list[RouteResult] = field(default_factory=list)
    total_distance: float = 0.0
    unreachable: list[str] = field(default_factory=list)

    @property
    def all_waypoints(self) -> list[RoutePoint]:
        """全レグを連結したウェイポイント列（先頭の重複ノードは除去して連続させる）。"""
        points: list[RoutePoint] = []
        for leg in self.legs:
            leg_points = leg.waypoints
            if points and leg_points and points[-1].id == leg_points[0].id:
                leg_points = leg_points[1:]
            points.extend(leg_points)
        return points


class RouteGraphBuilder:
    """store_map のウェイポイント・グラフを構築し、最短経路・巡回順を計算する。"""

    def __init__(
        self,
        floors: list[dict[str, Any]],
        inter_floor_edges: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        # 店内の通路は双方向に通行できるため無向グラフで表現する。
        self._graph: nx.Graph = nx.Graph()
        self._nodes: dict[str, dict[str, Any]] = {}

        for floor_data in floors:
            for wp in floor_data.get("waypoints", []):
                self._add_node(wp)
            for edge in floor_data.get("edges", []):
                self._add_edge(edge)

        for edge in inter_floor_edges or []:
            self._add_edge(edge)

    # -- 構築ヘルパ ---------------------------------------------------------
    def _add_node(self, wp: dict[str, Any]) -> None:
        node_id = wp["id"]
        self._nodes[node_id] = wp
        self._graph.add_node(node_id)

    def _add_edge(self, edge: dict[str, Any]) -> None:
        self._graph.add_edge(edge["from"], edge["to"], distance=float(edge["distance"]))

    @classmethod
    def from_store_map(cls, store_map: dict[str, Any]) -> "RouteGraphBuilder":
        return cls(store_map.get("floors", []), store_map.get("inter_floor_edges", []))

    @classmethod
    def from_store_map_file(cls, path: Union[str, Path]) -> "RouteGraphBuilder":
        text = Path(path).read_text(encoding="utf-8")
        store_map = json.loads(text)
        return cls.from_store_map(store_map)

    # -- 参照 -----------------------------------------------------------
    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def get_node(self, node_id: str) -> Optional[dict[str, Any]]:
        return self._nodes.get(node_id)

    def node_ids(self) -> list[str]:
        return list(self._nodes.keys())

    def nearest_node(
        self, floor: int, x: float, y: float, node_type: Optional[str] = None
    ) -> str:
        """指定フロア上で(x, y)に最も近いウェイポイントIDを返す（QR/商品座標→ノード解決用）。

        Raises:
            RouteNotFoundError: 条件に合うノードがフロア上に1つも無い場合。
        """
        candidates = [
            (node_id, wp)
            for node_id, wp in self._nodes.items()
            if wp.get("floor") == floor and (node_type is None or wp.get("type") == node_type)
        ]
        if not candidates:
            raise RouteNotFoundError(
                f"floor={floor} type={node_type} に該当するウェイポイントがありません"
            )
        best_id, _ = min(
            candidates, key=lambda item: (item[1]["x"] - x) ** 2 + (item[1]["y"] - y) ** 2
        )
        return best_id

    def _to_point(self, node_id: str) -> RoutePoint:
        wp = self._nodes[node_id]
        return RoutePoint(id=node_id, floor=wp["floor"], x=wp["x"], y=wp["y"], type=wp["type"])

    # -- 経路計算 ---------------------------------------------------------
    def shortest_path(self, start_id: str, end_id: str) -> RouteResult:
        """start_id -> end_id の最短経路（ウェイポイント座標列）を返す。

        エッジケース:
        - start_id == end_id（同一地点）: 距離0・単一ノードの結果を返す。
        - 未知のノードID／到達不能（別成分・別フロアで階段/EV未接続等）:
          `RouteNotFoundError` を送出する。
        """
        if start_id not in self._nodes or end_id not in self._nodes:
            raise RouteNotFoundError(f"未知のウェイポイント: start={start_id} end={end_id}")

        if start_id == end_id:
            point = self._to_point(start_id)
            return RouteResult(waypoints=[point], total_distance=0.0, floors=[point.floor])

        try:
            path = nx.shortest_path(self._graph, start_id, end_id, weight="distance")
        except nx.NetworkXNoPath as exc:
            raise RouteNotFoundError(f"経路が見つかりません: {start_id} -> {end_id}") from exc

        distance = nx.path_weight(self._graph, path, weight="distance")
        points = [self._to_point(n) for n in path]
        floors = sorted({p.floor for p in points})
        return RouteResult(waypoints=points, total_distance=float(distance), floors=floors)

    def multi_destination_route(
        self, start_id: str, destination_ids: list[str]
    ) -> MultiRouteResult:
        """複数目的地（コーディネート構成品等）の巡回順を提案する。

        アルゴリズム: 最近傍法（nearest neighbor heuristic）。
        理由（コメント）: 巡回順の厳密最適化は巡回セールスマン問題(TSP)であり
        目的地数nに対し計算量が爆発する。店内案内で想定する目的地数は
        コーディネート構成品程度（実務上せいぜい数点〜十数点）であり、
        リアルタイムにAPI応答を返す必要があるため、実装の単純さと応答速度を
        優先し、常に「現在地から最も近い未訪問の目的地」を選ぶ貪欲法（最近傍法）を
        採用する。最適性は厳密には保証されないが、店内回遊の実用上は十分な近似となる。

        到達不能な目的地（別フロアで階段/EV未接続等）は `unreachable` に積んで
        処理を継続する（例外にしない＝安全なエッジケース処理）。
        """
        remaining = list(dict.fromkeys(destination_ids))  # 重複除去（順序維持）
        current = start_id
        order: list[str] = []
        legs: list[RouteResult] = []
        total_distance = 0.0
        unreachable: list[str] = []

        while remaining:
            best_dest = None
            best_result: Optional[RouteResult] = None
            for dest in remaining:
                try:
                    result = self.shortest_path(current, dest)
                except RouteNotFoundError:
                    continue
                if best_result is None or result.total_distance < best_result.total_distance:
                    best_dest = dest
                    best_result = result
            if best_dest is None or best_result is None:
                # 残り全てが現在地から到達不能
                unreachable.extend(remaining)
                break
            order.append(best_dest)
            legs.append(best_result)
            total_distance += best_result.total_distance
            current = best_dest
            remaining.remove(best_dest)

        return MultiRouteResult(
            order=order, legs=legs, total_distance=total_distance, unreachable=unreachable
        )
