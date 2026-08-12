"""候補データに応じて質問を選ぶポリシー。

質問を先に固定せず、回答が実際にランキングを変えられる場合だけ表示する。特に現行
商品データは色の欠損が多いため、候補内で十分な色データが揃う場合に限って色を尋ねる。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from recommender import RelatedItem


@dataclass(frozen=True)
class QuestionOption:
    option_id: str
    label: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {
            "option_id": self.option_id,
            "label": self.label,
            "description": self.description,
        }


@dataclass(frozen=True)
class GuidedQuestion:
    question_id: str
    text: str
    reason: str
    options: tuple[QuestionOption, ...]

    def as_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "text": self.text,
            "reason": self.reason,
            "options": [option.as_dict() for option in self.options],
        }


class QuestionPolicy:
    """最大3問を、候補の欠損状況と回答履歴から適応的に選ぶ。"""

    MAX_QUESTIONS = 3
    COLOR_COVERAGE_THRESHOLD = 0.60

    def next_question(
        self,
        related: list[RelatedItem],
        answered_question_ids: list[str],
        *,
        has_coordinate_partners: bool = False,
    ) -> GuidedQuestion | None:
        if len(answered_question_ids) >= self.MAX_QUESTIONS:
            return None
        answered = set(answered_question_ids)
        for question in self._available_questions(
            related, has_coordinate_partners=has_coordinate_partners
        ):
            if question.question_id not in answered:
                return question
        return None

    def _available_questions(
        self, related: list[RelatedItem], *, has_coordinate_partners: bool = False
    ) -> list[GuidedQuestion]:
        questions: list[GuidedQuestion] = []
        focus_question = self._focus_question(
            related, has_coordinate_partners=has_coordinate_partners
        )
        # 「関連性を維持」しか選べない場合、聞いても結果は変わらないため質問自体を省く。
        if len(focus_question.options) >= 2:
            questions.append(focus_question)

        categories = Counter(item.cat_mid for item in related if item.cat_mid)
        if len(categories) >= 2:
            options = tuple(
                QuestionOption(
                    option_id=f"category:{category}",
                    label=category,
                    description=f"{category}の候補を上位にします。",
                )
                for category, _ in categories.most_common(3)
            ) + (
                QuestionOption("no_preference", "まだ決めていない", "元の関連度を維持します。"),
            )
            questions.append(
                GuidedQuestion(
                    question_id="category",
                    text="どの商品種類から見てみたいですか？",
                    reason="種類を先に選ぶと、候補を短時間で絞れます。",
                    options=options,
                )
            )

        color_question = self._color_question(related)
        if color_question is not None:
            questions.append(color_question)
        else:
            route_question = self._route_question(related)
            if route_question is not None:
                questions.append(route_question)
        return questions

    @staticmethod
    def _focus_question(
        related: list[RelatedItem], *, has_coordinate_partners: bool
    ) -> GuidedQuestion:
        options = [
            QuestionOption(
                "relevance",
                "関連性を優先",
                "併売リフトと既存の関連度をそのまま重視します。",
            )
        ]
        if has_coordinate_partners:
            options.append(
                QuestionOption(
                    "harmony",
                    "まとまり・相性",
                    "登録済みコーディネートで一緒に使われる商品を重視します。",
                )
            )
        prices = {float(item.product.get("price") or 0) for item in related}
        if len(prices) >= 2:
            options.append(
                QuestionOption(
                    "budget",
                    "価格を抑える",
                    "候補内で価格を抑えやすい商品を重視します。",
                )
            )
        signatures = {
            (
                item.cat_mid,
                str(item.product.get("color") or ""),
                int(float(item.product.get("price") or 0) // 5_000),
                item.product.get("floor"),
                item.product.get("zone"),
                item.high_lift_low_corate,
            )
            for item in related
        }
        if len(signatures) >= 2:
            options.append(
                QuestionOption(
                    "discovery",
                    "新しい組み合わせ",
                    "関連性を保ち、種類・価格帯・色・売場の違う候補を探索します。",
                )
            )
        return GuidedQuestion(
            question_id="focus",
            text="今回、何を優先して候補を見たいですか？",
            reason="おすすめの方向を最初に決めると、入力を繰り返さずに済みます。",
            options=tuple(options),
        )

    def _color_question(self, related: list[RelatedItem]) -> GuidedQuestion | None:
        if not related:
            return None
        colors = Counter(
            str(item.product.get("color"))
            for item in related
            if item.product.get("color")
        )
        coverage = sum(colors.values()) / len(related)
        if coverage < self.COLOR_COVERAGE_THRESHOLD or len(colors) < 2:
            return None
        options = tuple(
            QuestionOption(
                option_id=f"color:{color}",
                label=color,
                description=f"{color}の商品を上位にします。",
            )
            for color, _ in colors.most_common(3)
        ) + (QuestionOption("no_preference", "色は指定しない", "色による並べ替えを行いません。"),)
        return GuidedQuestion(
            question_id="color",
            text="合わせたい色はありますか？",
            reason="現在の候補には比較できる色データが揃っています。",
            options=options,
        )

    @staticmethod
    def _route_question(related: list[RelatedItem]) -> GuidedQuestion | None:
        options: list[QuestionOption] = []
        locations = {
            (
                item.product.get("floor"),
                item.product.get("x"),
                item.product.get("y"),
            )
            for item in related
        }
        if len(locations) >= 2:
            options.append(
                QuestionOption(
                    "closest",
                    "近い売場から",
                    "起点商品から比較的近い候補を重視します。",
                )
            )
        sub_passage_values = {
            bool(item.product.get("sub_passage_flag")) for item in related
        }
        if sub_passage_values == {False, True}:
            options.append(
                QuestionOption(
                    "sub_passage",
                    "途中の候補も見る",
                    "サブ通路で見つけやすい候補を重視します。",
                )
            )
        options.append(
            QuestionOption("relevance", "相性を優先", "売場距離では並べ替えません。")
        )
        if len(options) == 1:
            return None
        return GuidedQuestion(
            question_id="route",
            text="売場では、どの見方がよさそうですか？",
            reason="最後に店内での回り方を合わせます。",
            options=tuple(options),
        )
