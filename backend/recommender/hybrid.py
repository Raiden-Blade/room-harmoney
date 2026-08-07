"""ハイブリッド推薦ロジック（5章 / DESIGN.md B1）。

データドリブン（中分類併売率からのリフト近似・DECISIONS.md #2）と
キュレーション（コーディネートマスタ）を重み付け合成して関連商品を並べる。

テスト容易性のため、コンストラクタは products/co_purchase/coordinates を
「データ注入」で受け取る（`HybridRecommender(products=..., co_purchase=..., coordinates=...)`）。
本番/APIからの利用は `HybridRecommender.from_data_dir()` で data/ のJSONを読み込む。
"""
from typing import Any, Optional

from dataio import load_json_list

from . import RecommendationResult, RecommenderInterface, RelatedItem
from .config import DEFAULT_WEIGHTS


class HybridRecommender(RecommenderInterface):
    """中分類リフト（データドリブン）とコーディネート適合度（キュレーション）のハイブリッド推薦。"""

    def __init__(
        self,
        products: list[dict[str, Any]],
        co_purchase: list[dict[str, Any]],
        coordinates: list[dict[str, Any]],
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        self._products = list(products or [])
        self._co_purchase = list(co_purchase or [])
        self._coordinates = list(coordinates or [])
        self._default_weights = {**DEFAULT_WEIGHTS, **(weights or {})}

        self._products_by_id: dict[str, dict[str, Any]] = {
            p["product_id"]: p for p in self._products if "product_id" in p
        }
        # 中分類 -> その中分類に属する商品一覧（起点商品自身を除く判定は呼び出し側で行う）
        self._products_by_mid: dict[str, list[dict[str, Any]]] = {}
        for p in self._products:
            self._products_by_mid.setdefault(p.get("cat_mid"), []).append(p)

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Optional[str] = None,
        weights: Optional[dict[str, float]] = None,
    ) -> "HybridRecommender":
        """data/ のJSON（products.json, co_purchase.json, coordinates.json）から構築する。

        いずれかのファイルが欠損/空でも `load_json_list` が空リストにフォールバックするため、
        本番投入前でも例外にならず「関連ゼロ・コーデゼロ」として安全に動作する。
        """
        products = load_json_list("products.json", data_dir=data_dir)
        co_purchase = load_json_list("co_purchase.json", data_dir=data_dir)
        coordinates = load_json_list("coordinates.json", data_dir=data_dir)
        return cls(products, co_purchase, coordinates, weights=weights)

    def _co_purchase_lift_map(self, origin_mid: str) -> dict[str, tuple[float, bool]]:
        """起点の中分類と組になる他中分類 -> (lift, high_lift_low_corate) を集める。

        同じ中分類ペアが重複して現れる場合はリフトが最大のものを採用する（安全側）。
        """
        result: dict[str, tuple[float, bool]] = {}
        for row in self._co_purchase:
            a, b = row.get("cat_mid_a"), row.get("cat_mid_b")
            if a == origin_mid and b is not None:
                other = b
            elif b == origin_mid and a is not None:
                other = a
            else:
                continue
            lift = float(row.get("lift", 0.0))
            flag = bool(row.get("high_lift_low_corate", False))
            if other not in result or lift > result[other][0]:
                result[other] = (lift, flag)
        return result

    def recommend(
        self,
        product_id: str,
        weights: Optional[dict[str, float]] = None,
        member_id: Optional[str] = None,
    ) -> RecommendationResult:
        # member_id はフェーズ3-A（DECISIONS.md 改訂#5-A）の後方互換引数。
        # HybridRecommender はデータドリブン＋キュレーションの「base」実装であり、
        # 会員個人最適化は `recommender.personalized.PersonalizedRecommender` が
        # このクラスを合成（コンポジション）して上乗せする。ここでは無視してよい
        # （常に今までどおりの結果を返す＝呼び出し側の後方互換を担保する）。
        del member_id
        w = {**self._default_weights, **(weights or {})}

        origin = self._products_by_id.get(product_id)
        if origin is None:
            # エッジケース: 未知の product_id。例外にせず空の結果を安全に返す。
            return RecommendationResult(product_id=product_id, related=[], coordinates=[], product_found=False)

        origin_mid = origin.get("cat_mid")

        # --- コーディネート（キュレーション由来）: 起点商品を構成に含むものだけ ---
        coords_with_origin = [
            c for c in self._coordinates if product_id in (c.get("product_ids") or [])
        ]
        origin_coord_partner_ids: set[str] = set()
        for c in coords_with_origin:
            origin_coord_partner_ids.update(c.get("product_ids") or [])
        origin_coord_partner_ids.discard(product_id)

        # --- 関連商品（データドリブン: 中分類リフト） ---
        lift_map = self._co_purchase_lift_map(origin_mid) if origin_mid else {}

        related: list[RelatedItem] = []
        for other_mid, (lift, high_flag) in lift_map.items():
            for cand in self._products_by_mid.get(other_mid, []):
                if cand.get("product_id") == product_id:
                    continue
                # ハイブリッド統合: リフト項に「伸びしろ」ブーストを乗算し、
                # コーディネート適合度（起点商品と同じコーデに含まれるか）を加算する。
                boost = w["high_lift_low_corate_boost"] if high_flag else 1.0
                coordinate_affinity = 1.0 if cand["product_id"] in origin_coord_partner_ids else 0.0
                score = w["lift_weight"] * lift * boost + w["coordinate_weight"] * coordinate_affinity
                related.append(
                    RelatedItem(
                        product=cand,
                        cat_mid=other_mid,
                        lift=lift,
                        high_lift_low_corate=high_flag,
                        score=score,
                    )
                )

        # スコア降順。タイブレークはリフト降順→product_id昇順で決定的な並びにする。
        related.sort(key=lambda r: (-r.score, -r.lift, r.product.get("product_id", "")))

        return RecommendationResult(
            product_id=product_id,
            related=related,
            coordinates=coords_with_origin,
            product_found=True,
        )
