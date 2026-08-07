"""会員購入履歴パーソナライズ推薦（B1 PersonalizedRecommender）の単体テスト。
フェーズ3-A / DECISIONS.md 改訂#5-A → G1 単体ゲート。

重点観点（実装指示より）:
  (1) member_id なし → base(HybridRecommender) と完全一致（後方互換）
  (2) 履歴に存在しない未知の member_id → base と完全一致
  (3) 該当会員の購入履歴が空 → base と完全一致
  (4) アフィニティのある会員 → 並び順が変わる（具体順序を検証）
  (5) member_affinity_weight 引数での重み上書きで並びが変わる（0にすればbaseへ戻る）
  (6) 決定性（同一入力で複数回呼んでも同じ結果）
  (7) product_id 解決（purchased の product_id エントリを cat_mid に解決してアフィニティに使う）
  (8) from_data_dir: member_history.json 欠損時は空扱い（=base動作）
"""
from recommender import RecommendationResult, RecommenderInterface
from recommender.hybrid import HybridRecommender
from recommender.personalized import PersonalizedRecommender


def _product(product_id: str, cat_mid: str, **extra) -> dict:
    base = {"product_id": product_id, "name": product_id, "cat_mid": cat_mid}
    base.update(extra)
    return base


def _pair(a: str, b: str, lift: float, high_flag: bool = False) -> dict:
    return {
        "cat_mid_a": a,
        "cat_mid_b": b,
        "co_purchase_rate": 0.05,
        "support": 0.05,
        "confidence": 0.2,
        "lift": lift,
        "high_lift_low_corate": high_flag,
    }


def _make_base() -> HybridRecommender:
    """P1(A) を起点に、B(lift1.0)・C(lift1.1) が関連候補になるベース推薦。

    base の並びは常に PC(lift1.1) > PB(lift1.0)（コーディネートなし・重みデフォルト）。
    """
    products = [
        _product("P1", "A"),
        _product("PB", "B"),
        _product("PC", "C"),
    ]
    co_purchase = [
        _pair("A", "B", lift=1.0),
        _pair("A", "C", lift=1.1),
    ]
    return HybridRecommender(products=products, co_purchase=co_purchase, coordinates=[])


def _member_history() -> list[dict]:
    return [
        {
            "member_id": "M-AFFINITY",
            # cat_mid "B" を5回購入している会員。デフォルト重み0.15なら
            # score'_PB = 1.0 * (1 + 0.15*5) = 1.75 > score_PC(=1.1) となり順位が入れ替わる。
            "purchased": [{"cat_mid": "B", "count": 5}],
        },
        {
            "member_id": "M-EMPTY",
            "purchased": [],
        },
        {
            "member_id": "M-PRODUCT-REF",
            # product_id 経由でも cat_mid に解決されアフィニティに使われることを確認する会員。
            # PB(cat_mid=B) を3回購入 -> score'_PB = 1.0*(1+0.15*3) = 1.45 > 1.1(PC)。
            "purchased": [{"product_id": "PB", "count": 3}],
        },
    ]


def _products_for_history() -> list[dict]:
    return [_product("P1", "A"), _product("PB", "B"), _product("PC", "C")]


def test_no_member_id_matches_base_exactly():
    """(1) member_id を渡さなければ base と完全に同一の結果（オブジェクトとして同一）。"""
    base = _make_base()
    rec = PersonalizedRecommender(
        base=base, member_history=_member_history(), products=_products_for_history()
    )

    base_result = base.recommend("P1")
    personalized_result = rec.recommend("P1")

    # HybridRecommender.recommend() は呼び出しごとに新しいオブジェクトを生成するため
    # ここでは値の完全一致（related/coordinates/product_found すべて）を検証する
    # （実装が「base結果をそのまま返す」ことによる恒等性は test_passthrough_returns_the_exact_base_object_instance で別途検証する）。
    assert personalized_result == base_result
    assert [item.product["product_id"] for item in personalized_result.related] == ["PC", "PB"]


def test_unknown_member_id_matches_base_exactly():
    """(2) 履歴に存在しない member_id は base と完全一致。"""
    base = _make_base()
    rec = PersonalizedRecommender(
        base=base, member_history=_member_history(), products=_products_for_history()
    )

    base_result = base.recommend("P1")
    result = rec.recommend("P1", member_id="M-DOES-NOT-EXIST")

    assert result == base_result


def test_member_with_empty_purchase_history_matches_base_exactly():
    """(3) 購入履歴が空の会員は base と完全一致。"""
    base = _make_base()
    rec = PersonalizedRecommender(
        base=base, member_history=_member_history(), products=_products_for_history()
    )

    base_result = base.recommend("P1")
    result = rec.recommend("P1", member_id="M-EMPTY")

    assert result == base_result


def test_passthrough_returns_the_exact_base_object_instance():
    """(1)(2)(3) の内部実装検証: base.recommend() の戻り値をそのまま return しているか
    （再実装によるロジックのズレを構造的に防ぐ設計になっているか）を、スタブの
    base recommender（毎回同一インスタンスを返す）で恒等性チェックする。
    """
    sentinel = RecommendationResult(product_id="P1", related=[], coordinates=[], product_found=True)

    class _StubBase(RecommenderInterface):
        def recommend(self, product_id, weights=None, member_id=None):
            return sentinel

    rec = PersonalizedRecommender(
        base=_StubBase(), member_history=_member_history(), products=_products_for_history()
    )

    assert rec.recommend("P1") is sentinel
    assert rec.recommend("P1", member_id="M-DOES-NOT-EXIST") is sentinel
    assert rec.recommend("P1", member_id="M-EMPTY") is sentinel


def test_affinity_member_changes_ranking_order():
    """(4) アフィニティのある会員は、base のリフト順から並びが変わる（具体順序を検証）。"""
    base = _make_base()
    rec = PersonalizedRecommender(
        base=base, member_history=_member_history(), products=_products_for_history()
    )

    base_result = base.recommend("P1")
    assert [item.product["product_id"] for item in base_result.related] == ["PC", "PB"]

    personalized = rec.recommend("P1", member_id="M-AFFINITY")

    assert [item.product["product_id"] for item in personalized.related] == ["PB", "PC"]
    # スコアはブーストされているが、lift・high_lift_low_corate・product は不変。
    pb_item = personalized.related[0]
    pc_item = personalized.related[1]
    assert pb_item.product["product_id"] == "PB"
    assert pb_item.lift == 1.0
    assert pb_item.score == 1.0 * (1 + 0.15 * 5)
    assert pc_item.score == 1.1  # アフィニティ対象外(cat_mid=C)なのでスコア不変


def test_affinity_weight_override_changes_ranking():
    """(5) member_affinity_weight を0で上書きすると base と同じ並びに戻る。"""
    base = _make_base()
    rec = PersonalizedRecommender(
        base=base, member_history=_member_history(), products=_products_for_history()
    )

    boosted = rec.recommend("P1", member_id="M-AFFINITY")
    assert [item.product["product_id"] for item in boosted.related] == ["PB", "PC"]

    no_boost = rec.recommend("P1", member_id="M-AFFINITY", member_affinity_weight=0.0)
    assert [item.product["product_id"] for item in no_boost.related] == ["PC", "PB"]
    assert no_boost.related[0].score == 1.1
    assert no_boost.related[1].score == 1.0

    # 呼び出し引数の重みはコンストラクタのデフォルトより優先される
    stronger = rec.recommend("P1", member_id="M-AFFINITY", member_affinity_weight=1.0)
    assert stronger.related[0].score == 1.0 * (1 + 1.0 * 5)


def test_deterministic_repeated_calls_return_equal_results():
    """(6) 同一入力を複数回呼んでも同じ順序・同じスコアになる（決定性）。"""
    base = _make_base()
    rec = PersonalizedRecommender(
        base=base, member_history=_member_history(), products=_products_for_history()
    )

    first = rec.recommend("P1", member_id="M-AFFINITY")
    second = rec.recommend("P1", member_id="M-AFFINITY")

    assert [item.product["product_id"] for item in first.related] == [
        item.product["product_id"] for item in second.related
    ]
    assert [item.score for item in first.related] == [item.score for item in second.related]


def test_purchase_history_by_product_id_resolves_to_cat_mid():
    """(7) purchased の product_id エントリは products マスタで cat_mid に解決されアフィニティに使われる。"""
    base = _make_base()
    rec = PersonalizedRecommender(
        base=base, member_history=_member_history(), products=_products_for_history()
    )

    result = rec.recommend("P1", member_id="M-PRODUCT-REF")

    assert [item.product["product_id"] for item in result.related] == ["PB", "PC"]
    assert result.related[0].score == 1.0 * (1 + 0.15 * 3)


def test_from_data_dir_without_member_history_file_falls_back_to_base_behavior(tmp_path):
    """(8) member_history.json が無いディレクトリでも例外にならず、base動作のまま。"""
    import json

    products = _products_for_history()
    co_purchase = [_pair("A", "B", lift=1.0), _pair("A", "C", lift=1.1)]
    (tmp_path / "products.json").write_text(json.dumps(products), encoding="utf-8")
    (tmp_path / "co_purchase.json").write_text(json.dumps(co_purchase), encoding="utf-8")
    (tmp_path / "coordinates.json").write_text(json.dumps([]), encoding="utf-8")
    # member_history.json をあえて置かない。

    rec = PersonalizedRecommender.from_data_dir(data_dir=str(tmp_path))

    result_no_member = rec.recommend("P1")
    result_with_member = rec.recommend("P1", member_id="ANYONE")

    assert [item.product["product_id"] for item in result_no_member.related] == ["PC", "PB"]
    assert [item.product["product_id"] for item in result_with_member.related] == ["PC", "PB"]
