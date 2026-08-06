"""推薦ロジック（B1 HybridRecommender）の単体テスト。18.1 / DESIGN.md B1 → G1 単体ゲート。

重点観点（実装指示より）:
  (1) リフト降順で並ぶ
  (2) high_lift_low_corate が優先される
  (3) ハイブリッド重み（コーディネート適合度の重み）で並び順が変わる
  (4) 未知ID / 関連ゼロ / コーデゼロを安全に扱う
  (5) コーデに起点商品を含むものだけ返る
"""
from recommender.hybrid import HybridRecommender


def _product(product_id: str, cat_mid: str, **extra) -> dict:
    base = {"product_id": product_id, "name": product_id, "cat_mid": cat_mid}
    base.update(extra)
    return base


def _pair(a: str, b: str, lift: float, high_flag: bool = False) -> dict:
    # co_purchase_rate/support/confidence はテストの主眼ではないため lift から機械的に埋める。
    return {
        "cat_mid_a": a,
        "cat_mid_b": b,
        "co_purchase_rate": 0.05,
        "support": 0.05,
        "confidence": 0.2,
        "lift": lift,
        "high_lift_low_corate": high_flag,
    }


def test_related_sorted_by_lift_descending():
    """(1) デフォルト重み・ブースト対象なしなら related はリフト降順で並ぶ。"""
    products = [
        _product("P1", "A"),
        _product("PB", "B"),
        _product("PC", "C"),
        _product("PD", "D"),
    ]
    co_purchase = [
        _pair("A", "B", lift=3.0),
        _pair("A", "C", lift=1.0),
        _pair("A", "D", lift=2.0),
    ]
    rec = HybridRecommender(products=products, co_purchase=co_purchase, coordinates=[])

    result = rec.recommend("P1")

    assert [item.product["product_id"] for item in result.related] == ["PB", "PD", "PC"]
    assert [item.lift for item in result.related] == [3.0, 2.0, 1.0]


def test_high_lift_low_corate_is_prioritized_over_equal_lift():
    """(2) 同じリフトでも high_lift_low_corate=true の方が優先的に押し上げられる。"""
    products = [
        _product("P1", "A"),
        _product("PE", "E"),  # high_lift_low_corate = True
        _product("PF", "F"),  # high_lift_low_corate = False
    ]
    co_purchase = [
        _pair("A", "E", lift=2.0, high_flag=True),
        _pair("A", "F", lift=2.0, high_flag=False),
    ]
    rec = HybridRecommender(products=products, co_purchase=co_purchase, coordinates=[])

    result = rec.recommend("P1")

    assert [item.product["product_id"] for item in result.related] == ["PE", "PF"]
    # ブーストにより E のスコアが F より厳密に高いこと（lift自体は同値）
    assert result.related[0].lift == result.related[1].lift == 2.0
    assert result.related[0].score > result.related[1].score


def test_hybrid_weight_changes_ranking_order():
    """(3) コーディネート適合度の重みを変えると related の並び順が変わる。"""
    products = [
        _product("P1", "A"),
        _product("PG", "G"),  # 起点と同じコーデに含まれる（適合度あり）・リフトはやや低い
        _product("PH", "H"),  # コーデには含まれない・リフトはやや高い
    ]
    co_purchase = [
        _pair("A", "G", lift=1.0),
        _pair("A", "H", lift=1.2),
    ]
    coordinates = [
        {
            "coordinate_id": "C1",
            "name": "test-coord",
            "theme": "test",
            "product_ids": ["P1", "PG"],
            "image_url": "",
            "total_price_estimate": 1000,
        }
    ]
    rec = HybridRecommender(products=products, co_purchase=co_purchase, coordinates=coordinates)

    # デフォルト重み（coordinate_weight=0.5）: コーデ適合ありの PG がリフト劣勢でも上位に来る
    default_result = rec.recommend("P1")
    assert [item.product["product_id"] for item in default_result.related] == ["PG", "PH"]

    # コーデ適合度の重みを0にすると、純粋にリフト順（PH が上位）へ並びが変わる
    no_coord_weight_result = rec.recommend("P1", weights={"coordinate_weight": 0.0})
    assert [item.product["product_id"] for item in no_coord_weight_result.related] == ["PH", "PG"]


def test_unknown_product_id_returns_empty_result_safely():
    """(4) 未知の product_id は例外を投げず、空の related/coordinates を返す。"""
    products = [_product("P1", "A")]
    rec = HybridRecommender(products=products, co_purchase=[], coordinates=[])

    result = rec.recommend("DOES-NOT-EXIST")

    assert result.product_found is False
    assert result.related == []
    assert result.coordinates == []


def test_no_related_co_purchase_returns_empty_related_list():
    """(4) 起点商品の中分類に該当する co_purchase が無い場合は related が空になる。"""
    products = [_product("P1", "A"), _product("P2", "B")]
    co_purchase = [_pair("X", "Y", lift=5.0)]  # 起点の中分類 "A" とは無関係
    rec = HybridRecommender(products=products, co_purchase=co_purchase, coordinates=[])

    result = rec.recommend("P1")

    assert result.product_found is True
    assert result.related == []


def test_no_matching_coordinates_returns_empty_coordinates_list():
    """(4) 起点商品を含むコーデが無い場合は coordinates が空になる。"""
    products = [_product("P1", "A"), _product("P2", "B")]
    coordinates = [
        {
            "coordinate_id": "C-OTHER",
            "name": "other",
            "theme": "other",
            "product_ids": ["P2"],
            "image_url": "",
            "total_price_estimate": 100,
        }
    ]
    rec = HybridRecommender(products=products, co_purchase=[], coordinates=coordinates)

    result = rec.recommend("P1")

    assert result.coordinates == []


def test_coordinates_only_include_ones_containing_origin_product():
    """(5) coordinates には起点商品を構成品に含むものだけが返る。"""
    products = [_product("P1", "A"), _product("P2", "B"), _product("P3", "C")]
    coordinates = [
        {
            "coordinate_id": "C-WITH-ORIGIN-1",
            "name": "with-origin-1",
            "theme": "t",
            "product_ids": ["P1", "P2"],
            "image_url": "",
            "total_price_estimate": 100,
        },
        {
            "coordinate_id": "C-WITHOUT-ORIGIN",
            "name": "without-origin",
            "theme": "t",
            "product_ids": ["P2", "P3"],
            "image_url": "",
            "total_price_estimate": 200,
        },
        {
            "coordinate_id": "C-WITH-ORIGIN-2",
            "name": "with-origin-2",
            "theme": "t",
            "product_ids": ["P1", "P3"],
            "image_url": "",
            "total_price_estimate": 300,
        },
    ]
    rec = HybridRecommender(products=products, co_purchase=[], coordinates=coordinates)

    result = rec.recommend("P1")

    returned_ids = {c["coordinate_id"] for c in result.coordinates}
    assert returned_ids == {"C-WITH-ORIGIN-1", "C-WITH-ORIGIN-2"}
