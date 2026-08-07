"""会員購入履歴に基づくパーソナライズ推薦（フェーズ3-A / DECISIONS.md 改訂#5-A）。

`data/member_history.json` の**任意スロット**（会員購入履歴）を用いて、ベース推薦
（`RecommenderInterface` 実装。既定では `HybridRecommender`）の `related` 並びを
「会員が過去に買った中分類への親和度（アフィニティ）」で再ランキングする。

後方互換の要（改訂#5-A の発注者承認条件そのもの）：
  - member_id が None（未指定）
  - member_id が履歴に存在しない（未知の会員）
  - 該当会員の購入履歴が空
のいずれかの場合は、**ベース推薦の結果をそのまま**返す。実装上もこれらのケースは
`base.recommend()` の戻り値オブジェクトをそのまま return することで、ロジックの
再実装によるズレ（別実装なら起こりうる浮動小数点誤差・並び不一致等）を構造的に防ぎ、
「base推薦と完全に同一の結果」を保証する。

アフィニティ式（5.3章「重みは設定値として外出しし、A/Bで調整可能にする」に準拠。
重みは `config.MEMBER_AFFINITY_WEIGHT` に外出し、呼び出し引数でも上書き可）：

    affinity_count(member, cat_mid)
        = 会員の購入履歴のうち、その中分類（related候補の cat_mid）の購入回数の合計。
          履歴エントリは `cat_mid` 直接指定、または `product_id` 指定（このクラスが
          products マスタで対応する cat_mid に解決する）のいずれかを取り、両方が
          同じ cat_mid を指す場合は合算する。

    score'(item) = score_base(item) * (1 + MEMBER_AFFINITY_WEIGHT * affinity_count(member, item.cat_mid))

base のスコア（中分類リフト×ハイブリッド重み。`HybridRecommender` 参照）を主信号として
維持したまま、アフィニティを**相対倍率**として乗算する（加点方式にしない）。
affinity_count が 0 の商品は score' = score_base（無変化）。これにより、リフト差が
大きい項目同士は多少のアフィニティでは順位が入れ替わりにくく、リフトが僅差の項目間では
アフィニティで順位が入れ替わりうる——という「リフトを主信号に保ったブースト」になる。

並びは決定的（score' 降順 → 元の score_base 降順 → lift 降順 → product_id 昇順）。
"""
from __future__ import annotations

from typing import Any, Optional

from dataio import load_json_dict, load_json_list

from . import RecommendationResult, RecommenderInterface, RelatedItem
from .config import MEMBER_AFFINITY_WEIGHT
from .hybrid import HybridRecommender


class PersonalizedRecommender(RecommenderInterface):
    """`RecommenderInterface` 実装。ベース推薦を会員アフィニティで再ランキングする。

    データドリブン（併売リフト）・キュレーション（コーディネート）はベース実装
    （既定 `HybridRecommender`）にすべて委譲し、本クラスは「会員購入履歴による
    再ランキング」という単一責務のみを持つ（責務分離。差し替え可能性を維持）。

    テスト容易性のため、コンストラクタは base/member_history/products を
    「データ注入」で受け取る。本番/APIからの利用は `from_data_dir()` を使う。
    """

    def __init__(
        self,
        base: RecommenderInterface,
        member_history: Optional[list[dict[str, Any]]] = None,
        products: Optional[list[dict[str, Any]]] = None,
        member_affinity_weight: Optional[float] = None,
    ) -> None:
        self._base = base
        self._default_affinity_weight = (
            MEMBER_AFFINITY_WEIGHT if member_affinity_weight is None else member_affinity_weight
        )

        products_by_id: dict[str, dict[str, Any]] = {
            p["product_id"]: p for p in (products or []) if "product_id" in p
        }

        # member_id -> {cat_mid: 購入回数の合計} に前計算しておく
        # （recommend() 呼び出しのたびに購入履歴全件を走査しなくてよいようにする）。
        self._affinity_by_member: dict[str, dict[str, int]] = {}
        for member in member_history or []:
            member_id = member.get("member_id")
            if not member_id:
                continue
            counts: dict[str, int] = {}
            for entry in member.get("purchased") or []:
                try:
                    count = int(entry.get("count", 1) or 0)
                except (TypeError, ValueError):
                    continue
                if count <= 0:
                    continue
                cat_mid = entry.get("cat_mid")
                if cat_mid is None:
                    ref_product_id = entry.get("product_id")
                    product = products_by_id.get(ref_product_id) if ref_product_id else None
                    cat_mid = product.get("cat_mid") if product else None
                if cat_mid is None:
                    # cat_mid が直接も product_id 経由でも解決できないエントリは
                    # 安全側（無視）。例外にはしない（母データの多少の欠損でも動作を維持）。
                    continue
                counts[cat_mid] = counts.get(cat_mid, 0) + count
            if counts:
                self._affinity_by_member[member_id] = counts

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Optional[str] = None,
        weights: Optional[dict[str, float]] = None,
        member_affinity_weight: Optional[float] = None,
    ) -> "PersonalizedRecommender":
        """data/ のJSON（products.json 等 + 任意スロット member_history.json）から構築する。

        `member_history.json` が存在しない/空/壊れている場合は `members: []` に
        フォールバックする（`load_json_dict` の欠損時フォールバック方針に準拠）ため、
        本スロット未投入でも例外にならず、常にベース推薦と完全に同一の結果で動作する。
        """
        base = HybridRecommender.from_data_dir(data_dir=data_dir, weights=weights)
        products = load_json_list("products.json", data_dir=data_dir)
        member_history = (
            load_json_dict("member_history.json", default={"members": []}, data_dir=data_dir).get(
                "members"
            )
            or []
        )
        return cls(
            base=base,
            member_history=member_history,
            products=products,
            member_affinity_weight=member_affinity_weight,
        )

    def recommend(
        self,
        product_id: str,
        weights: Optional[dict[str, float]] = None,
        member_id: Optional[str] = None,
        member_affinity_weight: Optional[float] = None,
    ) -> RecommendationResult:
        base_result = self._base.recommend(product_id, weights=weights)

        affinity = self._affinity_by_member.get(member_id) if member_id else None
        if not affinity or not base_result.related:
            # 後方互換（改訂#5-A の承認条件）: member_id 未指定／未知の会員／
            # 履歴が空のいずれかは、ベース推薦の結果をそのまま返す
            # （related が空の場合も再ランキングする意味が無いため同様に扱う）。
            return base_result

        w = (
            self._default_affinity_weight
            if member_affinity_weight is None
            else member_affinity_weight
        )

        # (再ランキング後のRelatedItem, 元のscore) のペアで保持し、元スコアをタイブレークに使う
        # （id() 等の間接参照に頼らず、生成した順序のまま安全にペアリングする）。
        reranked_with_orig: list[tuple[RelatedItem, float]] = []
        for item in base_result.related:
            count = affinity.get(item.cat_mid, 0)
            new_score = item.score * (1.0 + w * count)
            new_item = RelatedItem(
                product=item.product,
                cat_mid=item.cat_mid,
                lift=item.lift,
                high_lift_low_corate=item.high_lift_low_corate,
                score=new_score,
            )
            reranked_with_orig.append((new_item, item.score))

        # 決定的な並び: 新スコア降順 → 元スコア降順（同点タイブレーク） → リフト降順 → product_id昇順。
        reranked_with_orig.sort(
            key=lambda pair: (
                -pair[0].score,
                -pair[1],
                -pair[0].lift,
                pair[0].product.get("product_id", ""),
            )
        )
        reranked = [pair[0] for pair in reranked_with_orig]

        return RecommendationResult(
            product_id=base_result.product_id,
            related=reranked,
            coordinates=base_result.coordinates,
            product_found=base_result.product_found,
        )
