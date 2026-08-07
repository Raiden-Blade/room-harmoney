"""推薦ロジック層（5章 / DESIGN.md B1）。

`RecommenderInterface` は差し替え可能な推薦ロジックの抽象基底クラス。
実装（中分類併売率からのリフト近似＋ハイブリッド並び順）は `HybridRecommender`
（`backend/recommender/hybrid.py`）で行う（G1 ロジック）。

前提（コメントとして残す）：
step3 時点の雛形では `recommend(product_id) -> list[Any]` という単純なシグネチャ
だったが、5章「出力: related[]（リフト順）とcoordinates[]を持つ結果」を素直に
満たすには「関連商品」と「コーディネート」という**性質の異なる2つのリスト**を
返す必要がある。単一の list では両者を安全に区別できず API 層・フロント双方で
扱いにくくなるため、G1 実装時点で `RecommendationResult`（related/coordinates を
持つ構造体）を返す形にインターフェースを具体化する。責務（推薦ロジックと店舗
データの差し替え可能性）自体は変更していない。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RelatedItem:
    """関連商品1件分の推薦結果。"""

    product: dict[str, Any]
    cat_mid: str
    lift: float
    high_lift_low_corate: bool
    score: float


@dataclass
class RecommendationResult:
    """`recommend()` の戻り値。関連商品（データ由来）とコーディネート（キュレーション由来）を併記する。"""

    product_id: str
    related: list[RelatedItem] = field(default_factory=list)
    coordinates: list[dict[str, Any]] = field(default_factory=list)
    product_found: bool = True


class RecommenderInterface(ABC):
    """関連商品・コーディネート推薦ロジックの抽象インターフェース。

    データドリブン（リフト近似）とキュレーション（コーディネートマスタ）を
    ハイブリッドに扱う実装（例: HybridRecommender）で差し替え可能にする。
    """

    @abstractmethod
    def recommend(
        self,
        product_id: str,
        weights: Optional[dict[str, float]] = None,
        member_id: Optional[str] = None,
    ) -> RecommendationResult:
        """指定商品に対する関連商品・コーディネートの推薦結果を返す。

        Args:
            product_id: 起点となる商品ID。
            weights: ハイブリッド合成の重み設定（省略時はデフォルト重みを使用）。
                A/Bテスト等での重み調整のため引数で上書き可能にする。
            member_id: 会員ID（任意・フェーズ3-A / DECISIONS.md 改訂#5-A）。
                会員購入履歴に基づく個人最適化（`PersonalizedRecommender`）に対応する
                実装で使用する。**後方互換のため任意引数として追加**しており、
                `None`（未指定）の場合や、これを解釈しない実装（例: `HybridRecommender`
                そのもの）では無視され、常にベース推薦（今までどおりの挙動）を返す。

        Returns:
            RecommendationResult（related はスコア降順。未知の product_id や
            該当なしの場合も例外を投げず、空リストを持つ結果を返す）。
        """
        raise NotImplementedError
