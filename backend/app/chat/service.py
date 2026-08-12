"""ガイド型チャットのオーケストレーション。

状態はリクエストとレスポンスで往復させ、自由入力本文をDBへ保存しない。APIサーバ側に
会話専用テーブルを増やさないため、初版の運用コストとプライバシーリスクを抑えられる。
"""
from __future__ import annotations

from typing import Any

from recommender import RecommenderInterface, RelatedItem
from recommender.guided import GuidedReranker

from ..errors import ApiError
from ..repositories import ProductRepository
from ..schemas import ChatState, ChatTurnRequest
from .providers import ResponseComposer, TemplateResponseComposer
from .question_policy import GuidedQuestion, QuestionPolicy


class ChatService:
    """既存推薦、質問、回答解釈、説明文を一つのAPIレスポンスにまとめる。"""

    RECOMMENDATION_LIMIT = 6

    def __init__(
        self,
        recommender: RecommenderInterface,
        product_repo: ProductRepository,
        *,
        question_policy: QuestionPolicy | None = None,
        reranker: GuidedReranker | None = None,
        composer: ResponseComposer | None = None,
    ) -> None:
        self._recommender = recommender
        self._product_repo = product_repo
        self._policy = question_policy or QuestionPolicy()
        self._reranker = reranker or GuidedReranker()
        self._composer = composer or TemplateResponseComposer()

    def turn(self, body: ChatTurnRequest) -> dict[str, Any]:
        origin = self._product_repo.get(body.product_id)
        if origin is None:
            raise ApiError(404, "PRODUCT_NOT_FOUND", f"product_id={body.product_id} は見つかりません。")

        recommendation = self._recommender.recommend(body.product_id)
        has_coordinate_partners = self._has_coordinate_partners(
            recommendation.related, recommendation.coordinates
        )
        state = self._initial_state() if body.action == "start" else self._copy_state(body.state)
        staff_mode = body.mode == "staff"

        message = self._composer.opening(origin["name"], staff_mode=staff_mode)
        recognized = True
        if body.action in {"answer", "skip"}:
            current = self._policy.next_question(
                recommendation.related,
                state["answered_question_ids"],
                has_coordinate_partners=has_coordinate_partners,
            )
            if current is None:
                message = self._composer.completed(staff_mode=staff_mode)
            elif body.question_id != current.question_id:
                raise ApiError(
                    422,
                    "CHAT_QUESTION_MISMATCH",
                    "表示中の質問と回答対象が一致しません。会話を最初からやり直してください。",
                )
            elif body.action == "skip":
                state["answered_question_ids"].append(current.question_id)
                message = "この質問はスキップしました。"
            else:
                recognized = self._apply_answer(
                    state, current, body.answer_id, body.text, recommendation.related
                )
                if recognized:
                    state["answered_question_ids"].append(current.question_id)
                    message = self._composer.accepted(staff_mode=staff_mode)
                else:
                    message = self._composer.unrecognized()

        completed = body.action == "finish" or not recommendation.related
        next_question = None
        if not completed:
            next_question = self._policy.next_question(
                recommendation.related,
                state["answered_question_ids"],
                has_coordinate_partners=has_coordinate_partners,
            )
            if next_question is None:
                completed = True
        if completed and body.action != "start":
            message = self._composer.completed(staff_mode=staff_mode)

        guided_all = self._reranker.rerank(
            recommendation.related,
            origin=origin,
            coordinates=recommendation.coordinates,
            preferences=state["preferences"],
        )
        guided = self._select_for_display(guided_all, state["preferences"])

        return {
            "message": message,
            "recognized": recognized,
            "completed": completed,
            "question": next_question.as_dict() if next_question else None,
            "state": state,
            "recommendations": [
                {
                    "product": item.item.product,
                    "cat_mid": item.item.cat_mid,
                    "lift": item.item.lift,
                    "high_lift_low_corate": item.item.high_lift_low_corate,
                    "base_score": item.item.score,
                    "guided_score": item.guided_score,
                    "reasons": list(item.reasons)
                    + (
                        ["関連候補の中から、商品種類・価格帯・色・売場の違いも含めて探索"]
                        if state["preferences"].get("focus") == "discovery"
                        else []
                    )
                    + ([f"併売リフト: {item.item.lift:.2f}"] if staff_mode else []),
                }
                for item in guided
            ],
            "route_product_ids": self._bundle_ids(guided),
            "coordinates": recommendation.coordinates,
            "data_notice": (
                "現在の併売・売場データには実習用の仮想値が含まれます。実店舗での効果はPOS突合で検証します。"
            ),
        }

    @staticmethod
    def _initial_state() -> dict[str, Any]:
        return {"answered_question_ids": [], "preferences": {}}

    @staticmethod
    def _copy_state(state: ChatState) -> dict[str, Any]:
        return {
            "answered_question_ids": list(state.answered_question_ids),
            "preferences": dict(state.preferences),
        }

    def _apply_answer(
        self,
        state: dict[str, Any],
        question: GuidedQuestion,
        answer_id: str | None,
        text: str | None,
        related: list[RelatedItem],
    ) -> bool:
        selected = answer_id or self._interpret_text(text or "", question, related)
        valid_ids = {option.option_id for option in question.options}
        if not selected or selected not in valid_ids:
            return False
        if selected == "no_preference" or selected in {"balanced", "relevance"}:
            return True
        if question.question_id in {"category", "color"}:
            state["preferences"][question.question_id] = selected.split(":", 1)[1]
        else:
            state["preferences"][question.question_id] = selected
        return True

    @staticmethod
    def _interpret_text(
        text: str, question: GuidedQuestion, related: list[RelatedItem]
    ) -> str | None:
        normalized = text.strip().lower()
        if not normalized:
            return None
        keyword_map = {
            "budget": ("安", "予算", "価格", "節約"),
            "harmony": ("相性", "まとまり", "統一", "コーデ"),
            "discovery": ("新しい", "意外", "発見", "伸びしろ"),
            "closest": ("近", "早", "短"),
            "sub_passage": ("途中", "通路", "ついで"),
            "relevance": ("関連", "そのまま", "おまかせ"),
        }
        valid_ids = {option.option_id for option in question.options}
        for option_id, keywords in keyword_map.items():
            if option_id in valid_ids and any(keyword in normalized for keyword in keywords):
                return option_id
        for item in related:
            category = item.cat_mid
            color = str(item.product.get("color") or "")
            if f"category:{category}" in valid_ids and category.lower() in normalized:
                return f"category:{category}"
            if color and f"color:{color}" in valid_ids and color.lower() in normalized:
                return f"color:{color}"
        return None

    @staticmethod
    def _has_coordinate_partners(
        related: list[RelatedItem], coordinates: list[dict[str, Any]]
    ) -> bool:
        related_ids = {item.product.get("product_id") for item in related}
        coordinate_ids = {
            product_id
            for coordinate in coordinates
            for product_id in (coordinate.get("product_ids") or [])
        }
        return bool(related_ids & coordinate_ids)

    @staticmethod
    def _bundle_ids(guided: list) -> list[str]:
        """上位候補から異なる中分類を優先して最大3商品を束ねる。"""
        selected: list[str] = []
        seen_categories: set[str] = set()
        for item in guided:
            product_id = item.item.product.get("product_id")
            if not product_id or item.item.cat_mid in seen_categories:
                continue
            selected.append(product_id)
            seen_categories.add(item.item.cat_mid)
            if len(selected) == 3:
                break
        if len(selected) < 2:
            for item in guided:
                product_id = item.item.product.get("product_id")
                if product_id and product_id not in selected:
                    selected.append(product_id)
                if len(selected) == 3:
                    break
        return selected

    def _select_for_display(self, guided: list, preferences: dict[str, str]) -> list:
        """上位6件が同一カテゴリだけになる問題を、候補集合内の多様化で抑える。

        既存推薦器では同じ中分類の商品が同点になりやすく、APIで単純に上位N件を切ると
        6件すべてが同じ種類になることがある。これは「目当て以外の商品認知を広げる」
        課題と逆行する。明示的にカテゴリを選んだ後だけはその希望を優先し、それ以外は
        各カテゴリの上位商品を1件ずつ巡回して提示する。無関係な商品は追加せず、元の
        関連候補集合とカテゴリ内順位は維持する。
        """
        if preferences.get("category"):
            return guided[: self.RECOMMENDATION_LIMIT]
        if preferences.get("focus") == "discovery":
            return self._exploration_selection(guided)

        buckets: dict[str, list] = {}
        category_order: list[str] = []
        for item in guided:
            category = item.item.cat_mid
            if category not in buckets:
                buckets[category] = []
                category_order.append(category)
            buckets[category].append(item)

        selected: list = []
        while len(selected) < self.RECOMMENDATION_LIMIT:
            added = False
            for category in category_order:
                bucket = buckets[category]
                if not bucket:
                    continue
                selected.append(bucket.pop(0))
                added = True
                if len(selected) == self.RECOMMENDATION_LIMIT:
                    break
            if not added:
                break
        return selected

    def _exploration_selection(self, guided: list) -> list:
        """関連性を保ったまま、異なる属性を持つ候補を貪欲に選ぶ。

        商品単位の併売実績が無い現状では、「未知の商品が必ず合う」と推定する根拠はない。
        そこで探索の範囲を既存推薦器が返した関連候補に限定し、その中で商品種類・価格帯・
        既知の色・売場が重ならない候補を増やす。これは効果保証ではなく、比較可能な選択肢を
        広げるための決定的な多様化である。
        """
        if not guided:
            return []
        max_score = max(item.guided_score for item in guided) or 1.0
        remaining = list(enumerate(guided))
        selected: list = []
        seen_categories: set[str] = set()
        seen_colors: set[str] = set()
        seen_price_bands: set[str] = set()
        seen_locations: set[tuple] = set()

        while remaining and len(selected) < self.RECOMMENDATION_LIMIT:
            if not selected:
                # 1件目は必ず元の最上位候補にし、探索でも関連性のアンカーを失わない。
                chosen_pair = remaining[0]
            else:
                max_index = max(len(guided) - 1, 1)

                def exploration_value(pair: tuple[int, Any]) -> tuple[float, int]:
                    index, item = pair
                    product = item.item.product
                    category = item.item.cat_mid
                    color = str(product.get("color") or "")
                    price_band = self._price_band(float(product.get("price") or 0))
                    location = (product.get("floor"), product.get("zone"))
                    novelty = 0.0
                    novelty += 0.55 if category not in seen_categories else 0.0
                    novelty += 0.18 if color and color not in seen_colors else 0.0
                    novelty += 0.16 if price_band not in seen_price_bands else 0.0
                    novelty += 0.11 if location not in seen_locations else 0.0
                    novelty += 0.12 if item.item.high_lift_low_corate else 0.0
                    # 2件目以降は元ランキングの後方にある関連候補にも一定の探索余地を与える。
                    # ただし品質項を残すため、単純な逆順にはしない。
                    rank_novelty = 0.35 * index / max_index
                    quality = 0.55 * item.guided_score / max_score
                    return quality + novelty + rank_novelty, -index

                chosen_pair = max(remaining, key=exploration_value)
            remaining.remove(chosen_pair)
            chosen = chosen_pair[1]
            product = chosen.item.product
            selected.append(chosen)
            seen_categories.add(chosen.item.cat_mid)
            color = str(product.get("color") or "")
            if color:
                seen_colors.add(color)
            seen_price_bands.add(self._price_band(float(product.get("price") or 0)))
            seen_locations.add((product.get("floor"), product.get("zone")))
        return selected

    @staticmethod
    def _price_band(price: float) -> str:
        if price < 5_000:
            return "under_5000"
        if price < 20_000:
            return "under_20000"
        if price < 50_000:
            return "under_50000"
        return "over_50000"
