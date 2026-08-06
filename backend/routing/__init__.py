"""経路計算層（4.3章 / DESIGN.md B2）。

ウェイポイント・グラフ上の最短経路・複数目的地の巡回順の計算を担う（networkx を利用）。
実装本体は `graph.py`（`RouteGraphBuilder` ほか）。この `__init__.py` は主要な公開APIを
再エクスポートするのみ。
"""
from .graph import (
    MultiRouteResult,
    RouteGraphBuilder,
    RouteNotFoundError,
    RoutePoint,
    RouteResult,
)

__all__ = [
    "RouteGraphBuilder",
    "RouteNotFoundError",
    "RoutePoint",
    "RouteResult",
    "MultiRouteResult",
]
