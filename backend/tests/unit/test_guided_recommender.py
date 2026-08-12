"""ガイド型チャットの後段再ランキングと質問適応の単体テスト。"""
from __future__ import annotations

from app.chat.question_policy import QuestionPolicy
from app.chat.service import ChatService
from recommender import RelatedItem
from recommender.guided import GuidedReranker


ORIGIN = {
    "product_id": "ORIGIN",
    "name": "起点商品",
    "floor": 1,
    "x": 0,
    "y": 0,
}


def _item(
    product_id: str,
    *,
    price: int,
    score: float,
    category: str = "照明",
    color: str = "",
    discovery: bool = False,
    floor: int = 1,
    x: int = 10,
    sub_passage: bool = False,
) -> RelatedItem:
    return RelatedItem(
        product={
            "product_id": product_id,
            "name": product_id,
            "price": price,
            "color": color,
            "floor": floor,
            "x": x,
            "y": 0,
            "sub_passage_flag": sub_passage,
        },
        cat_mid=category,
        lift=score,
        high_lift_low_corate=discovery,
        score=score,
    )


def test_no_preferences_preserve_existing_order() -> None:
    related = [
        _item("P-HIGH", price=10000, score=2.0),
        _item("P-MID", price=5000, score=1.5),
        _item("P-LOW", price=1000, score=1.0),
    ]

    result = GuidedReranker().rerank(
        related, origin=ORIGIN, coordinates=[], preferences={}
    )

    assert [item.item.product["product_id"] for item in result] == [
        "P-HIGH",
        "P-MID",
        "P-LOW",
    ]


def test_budget_answer_can_raise_lower_price_candidate() -> None:
    related = [
        _item("P-EXPENSIVE", price=50000, score=2.0),
        _item("P-CHEAP", price=1000, score=1.9),
    ]

    result = GuidedReranker().rerank(
        related, origin=ORIGIN, coordinates=[], preferences={"focus": "budget"}
    )

    assert result[0].item.product["product_id"] == "P-CHEAP"
    assert any("価格" in reason for reason in result[0].reasons)


def test_discovery_answer_only_boosts_high_lift_low_corate_candidate() -> None:
    related = [
        _item("P-USUAL", price=5000, score=2.0),
        _item("P-UNTAPPED", price=5000, score=1.9, discovery=True),
    ]

    result = GuidedReranker().rerank(
        related, origin=ORIGIN, coordinates=[], preferences={"focus": "discovery"}
    )

    assert result[0].item.product["product_id"] == "P-UNTAPPED"
    assert any("伸びしろ" in reason for reason in result[0].reasons)


def test_color_question_is_omitted_when_candidate_coverage_is_low() -> None:
    related = [
        _item("P1", price=1000, score=2.0, color="ホワイト"),
        _item("P2", price=2000, score=1.9, category="ラグ", x=20),
        _item("P3", price=3000, score=1.8, category="収納", x=30, sub_passage=True),
    ]
    policy = QuestionPolicy()

    questions = policy._available_questions(related)

    assert "color" not in [question.question_id for question in questions]
    assert "route" in [question.question_id for question in questions]


def test_route_question_is_omitted_when_location_signals_cannot_change_order() -> None:
    related = [
        _item("P1", price=1000, score=2.0),
        _item("P2", price=2000, score=1.9),
    ]

    question = QuestionPolicy()._route_question(related)

    assert question is None


def test_color_question_is_used_only_when_values_can_change_ranking() -> None:
    related = [
        _item("P1", price=1000, score=2.0, color="ホワイト"),
        _item("P2", price=2000, score=1.9, color="ブラック"),
        _item("P3", price=3000, score=1.8, color="ホワイト"),
    ]
    policy = QuestionPolicy()

    questions = policy._available_questions(related)

    assert "color" in [question.question_id for question in questions]
    assert "route" not in [question.question_id for question in questions]


def test_question_policy_stops_after_three_answers() -> None:
    related = [
        _item("P1", price=1000, score=2.0, color="ホワイト"),
        _item("P2", price=2000, score=1.9, color="ブラック", category="ラグ"),
    ]

    question = QuestionPolicy().next_question(related, ["focus", "category", "color"])

    assert question is None


def test_focus_options_are_shown_only_when_they_have_a_usable_signal() -> None:
    same_candidates = [
        _item("P1", price=1000, score=2.0, color="ホワイト"),
        _item("P2", price=1000, score=1.9, color="ホワイト"),
    ]
    varied_candidates = [
        _item("P1", price=1000, score=2.0, color="ホワイト"),
        _item("P2", price=9000, score=1.9, category="ラグ", color="ブラック"),
    ]
    policy = QuestionPolicy()

    inactive_ids = {
        option.option_id
        for option in policy._focus_question(
            same_candidates, has_coordinate_partners=False
        ).options
    }
    active_ids = {
        option.option_id
        for option in policy._focus_question(
            varied_candidates, has_coordinate_partners=True
        ).options
    }

    assert inactive_ids == {"relevance"}
    assert active_ids == {"relevance", "harmony", "budget", "discovery"}


def test_display_selection_diversifies_categories_until_customer_selects_one() -> None:
    related = [
        _item("LIGHT-1", price=1000, score=2.0, category="照明"),
        _item("LIGHT-2", price=1100, score=1.9, category="照明"),
        _item("RUG-1", price=2000, score=1.8, category="ラグ"),
        _item("CURTAIN-1", price=3000, score=1.7, category="カーテン"),
    ]
    guided = GuidedReranker().rerank(
        related, origin=ORIGIN, coordinates=[], preferences={}
    )
    service = object.__new__(ChatService)

    diversified = service._select_for_display(guided, {})
    category_selected = service._select_for_display(guided, {"category": "照明"})

    assert [item.item.cat_mid for item in diversified[:3]] == ["照明", "ラグ", "カーテン"]
    assert [item.item.cat_mid for item in category_selected[:2]] == ["照明", "照明"]


def test_discovery_display_explores_different_observable_attributes() -> None:
    related = [
        _item("LIGHT-A", price=1000, score=2.0, category="照明", color="ホワイト", x=10),
        _item("LIGHT-B", price=1200, score=1.99, category="照明", color="ホワイト", x=10),
        _item("RUG-A", price=6000, score=1.9, category="ラグ", color="グレー", x=20),
        _item("SOFA-A", price=60000, score=1.8, category="ソファ", color="", floor=2),
        _item("CURTAIN-A", price=12000, score=1.7, category="カーテン", color="ブルー", x=30),
    ]
    guided = GuidedReranker().rerank(
        related, origin=ORIGIN, coordinates=[], preferences={"focus": "discovery"}
    )
    service = object.__new__(ChatService)

    ordinary = service._select_for_display(guided, {})
    explored = service._select_for_display(guided, {"focus": "discovery"})

    assert [item.item.product["product_id"] for item in explored] != [
        item.item.product["product_id"] for item in ordinary
    ]
    assert len({service._price_band(item.item.product["price"]) for item in explored}) >= 3
