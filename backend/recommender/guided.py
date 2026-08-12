"""ガイド型チャットボット向けの後段再ランキング。

既存の推薦器は候補生成の真実源として変更しない。本モジュールは、その戻り値を
来店客が会話で選んだ条件に合わせて並べ替えるだけに限定する。これにより、既存の
併売リフト・会員パーソナライズ・コーディネート適合度を壊さずに、店頭で説明可能な
追加信号を重ねられる。
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any

from . import RelatedItem


@dataclass(frozen=True)
class GuidedItem:
    """再ランキング後の商品と、画面に表示できる根拠。"""

    item: RelatedItem
    guided_score: float
    reasons: tuple[str, ...]


class GuidedReranker:
    """候補集合を維持したまま、回答に対応する説明可能な信号を加える。"""

    def rerank(
        self,
        related: list[RelatedItem],
        *,
        origin: dict[str, Any],
        coordinates: list[dict[str, Any]],
        preferences: dict[str, str],
    ) -> list[GuidedItem]:
        if not related:
            return []

        prices = [float(item.product.get("price") or 0) for item in related]
        distances = [self._distance(origin, item.product) for item in related]
        coordinate_partners = self._coordinate_partner_ids(origin.get("product_id"), coordinates)
        max_base_score = max((max(float(item.score), 0.0) for item in related), default=0.0)

        result: list[GuidedItem] = []
        for item in related:
            # 元スコアを最大値で正規化し、候補同士の「実際の差」を保つ。順位番号だけを
            # 0〜1へ割り当てると、候補が2件しかない場合に僅差でも0と1へ引き離され、
            # 顧客の明示回答が順位へ反映されなくなるため採用しない。
            base_quality = max(float(item.score), 0.0) / max_base_score if max_base_score else 0.0
            score = 0.70 * base_quality
            reasons = [f"{item.cat_mid}とのカテゴリ間の関連性を基に選定"]

            focus = preferences.get("focus")
            if focus == "budget":
                value = self._inverse_minmax(float(item.product.get("price") or 0), prices)
                score += 0.45 * value
                if value >= 0.66:
                    reasons.append("候補の中で価格を抑えやすい")
            elif focus == "harmony":
                in_coordinate = item.product.get("product_id") in coordinate_partners
                score += 0.45 if in_coordinate else 0.0
                if in_coordinate:
                    reasons.append("登録済みコーディネートで一緒に使われている")
            elif focus == "discovery":
                # 高リフト・低併売率フラグを、未開拓候補を探索するための明示信号にする。
                # フラグのない商品を無関係に持ち上げないことが重要である。
                score += 0.50 if item.high_lift_low_corate else 0.0
                if item.high_lift_low_corate:
                    reasons.append("関連性は高いが、現在の併売率には伸びしろがある")

            preferred_category = preferences.get("category")
            if preferred_category and item.cat_mid == preferred_category:
                score += 0.50
                reasons.append(f"選択した商品種類「{preferred_category}」に一致")

            preferred_color = preferences.get("color")
            if preferred_color and item.product.get("color") == preferred_color:
                score += 0.35
                reasons.append(f"希望色「{preferred_color}」に一致")

            route = preferences.get("route")
            if route == "closest":
                value = self._inverse_minmax(self._distance(origin, item.product), distances)
                score += 0.35 * value
                if value >= 0.66:
                    reasons.append("起点商品から比較的近い売場")
            elif route == "sub_passage" and item.product.get("sub_passage_flag"):
                score += 0.40
                reasons.append("サブ通路で見つけやすい売場")

            result.append(GuidedItem(item=item, guided_score=score, reasons=tuple(reasons)))

        result.sort(
            key=lambda guided: (
                # 商品種類を明示した回答は「探索したい」という一般的な傾向より強い意図として扱う。
                # スコア加点だけでは discovery の高リフト候補に負けるため、カテゴリ一致を
                # 第1ソートキーにして、一致商品の中で従来の品質・リフト順を維持する。
                bool(
                    preferences.get("category")
                    and guided.item.cat_mid != preferences["category"]
                ),
                -guided.guided_score,
                -guided.item.score,
                -guided.item.lift,
                guided.item.product.get("product_id", ""),
            )
        )
        return result

    @staticmethod
    def _coordinate_partner_ids(
        product_id: str | None, coordinates: list[dict[str, Any]]
    ) -> set[str]:
        partners: set[str] = set()
        if not product_id:
            return partners
        for coordinate in coordinates:
            product_ids = set(coordinate.get("product_ids") or [])
            if product_id in product_ids:
                partners.update(product_ids)
        partners.discard(product_id)
        return partners

    @staticmethod
    def _distance(origin: dict[str, Any], candidate: dict[str, Any]) -> float:
        """売場座標の概算距離。別フロアには固定ペナルティを加える。

        正確な経路は既存のRouteGraphBuilderが担当する。本値は質問に応じた候補の
        並べ替えだけに使い、「最短経路」とは表示しない。
        """
        floor_gap = abs(float(origin.get("floor") or 0) - float(candidate.get("floor") or 0))
        planar = hypot(
            float(origin.get("x") or 0) - float(candidate.get("x") or 0),
            float(origin.get("y") or 0) - float(candidate.get("y") or 0),
        )
        return planar + floor_gap * 100.0

    @staticmethod
    def _inverse_minmax(value: float, values: list[float]) -> float:
        minimum, maximum = min(values), max(values)
        if maximum == minimum:
            return 1.0
        return 1.0 - (value - minimum) / (maximum - minimum)
