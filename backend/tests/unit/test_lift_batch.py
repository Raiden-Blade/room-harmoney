"""リフト算出バッチ（`backend/batch/lift_batch.py`）の単体テスト。フェーズ2-A G1ゲート。

重点観点（実装指示より・手計算で検証）:
  (1) support/confidence/lift が手計算と一致する
  (2) high_lift_low_corate 判定が閾値どおり（境界値含む）
  (3) 再現性（同一入力を2回実行しても同一出力）
  (4) 出力スキーマの列が既存 co_purchase.json と一致
  (5) 参照整合: 生成された cat_mid が products.json に実在する
"""
import json

import pytest

from batch.lift_batch import (
    CORATE_THRESHOLD,
    LIFT_THRESHOLD,
    compute_metrics,
    run,
)
from dataio import load_json_list


def _source(category_support: dict, co_purchases: list[dict]) -> dict:
    return {
        "category_support": [
            {"cat_mid": cat_mid, "support": support}
            for cat_mid, support in category_support.items()
        ],
        "co_purchases": co_purchases,
    }


def test_metrics_match_hand_calculation():
    """(1) support_A=0.5, support_B=0.4, co_support=0.3 の手計算と一致すること。

    手計算:
      support(output)     = co_support           = 0.3
      confidence(A->B)    = co_support / support_A = 0.3 / 0.5 = 0.6
      lift                = co_support / (support_A * support_B) = 0.3 / (0.5*0.4) = 0.3/0.2 = 1.5
      co_purchase_rate    = co_support            = 0.3
    """
    source = _source(
        {"A": 0.5, "B": 0.4},
        [{"cat_mid_a": "A", "cat_mid_b": "B", "co_support": 0.3}],
    )

    rows = compute_metrics(source)

    assert len(rows) == 1
    row = rows[0]
    assert row["cat_mid_a"] == "A"
    assert row["cat_mid_b"] == "B"
    assert row["support"] == pytest.approx(0.3)
    assert row["co_purchase_rate"] == pytest.approx(0.3)
    assert row["confidence"] == pytest.approx(0.6)
    assert row["lift"] == pytest.approx(1.5)


def test_confidence_direction_is_a_to_b_not_symmetric():
    """(1) confidence は cat_mid_a -> cat_mid_b 方向。A/B を入れ替えると異なる値になる。

    手計算: support_A=0.2, support_B=0.8, co_support=0.1
      confidence(A->B) = 0.1 / 0.2 = 0.5
      confidence(B->A) は 0.1 / 0.8 = 0.125 で異なる（対称ではないことの確認）。
    """
    source = _source(
        {"A": 0.2, "B": 0.8},
        [{"cat_mid_a": "A", "cat_mid_b": "B", "co_support": 0.1}],
    )

    rows = compute_metrics(source)

    assert rows[0]["confidence"] == pytest.approx(0.5)
    assert rows[0]["confidence"] != pytest.approx(0.1 / 0.8)


def test_high_lift_low_corate_flag_true_when_both_conditions_met():
    """(2) lift >= LIFT_THRESHOLD かつ co_purchase_rate <= CORATE_THRESHOLD なら True。

    手計算: support_A=support_B=0.1, co_support=0.03（<=CORATE_THRESHOLD）
      lift = 0.03 / (0.1*0.1) = 3.0（>=LIFT_THRESHOLD）→ フラグ True。
    """
    assert CORATE_THRESHOLD == 0.045
    assert LIFT_THRESHOLD == 2.0

    source = _source(
        {"A": 0.1, "B": 0.1},
        [{"cat_mid_a": "A", "cat_mid_b": "B", "co_support": 0.03}],
    )

    rows = compute_metrics(source)

    assert rows[0]["lift"] == pytest.approx(3.0)
    assert rows[0]["co_purchase_rate"] == pytest.approx(0.03)
    assert rows[0]["high_lift_low_corate"] is True


def test_high_lift_low_corate_flag_false_when_lift_below_threshold():
    """(2) co_purchase_rate は低いが lift が閾値未満なら False。

    手計算: support_A=support_B=0.5, co_support=0.04（<=CORATE_THRESHOLD）
      lift = 0.04 / (0.5*0.5) = 0.16（<LIFT_THRESHOLD）→ フラグ False。
    """
    source = _source(
        {"A": 0.5, "B": 0.5},
        [{"cat_mid_a": "A", "cat_mid_b": "B", "co_support": 0.04}],
    )

    rows = compute_metrics(source)

    assert rows[0]["lift"] == pytest.approx(0.16)
    assert rows[0]["high_lift_low_corate"] is False


def test_high_lift_low_corate_flag_false_when_corate_above_threshold():
    """(2) lift は高いが co_purchase_rate が閾値超えなら False。

    手計算: support_A=support_B=0.5, co_support=0.3
      lift = 0.3 / (0.5*0.5) = 1.2 なので実は閾値未満だが、
      ここでは lift 単体は閾値以上/co_purchase_rate が閾値超のケースとして
      support_A=support_B=0.1, co_support=0.05 を使う。
      lift = 0.05 / (0.1*0.1) = 5.0（>=LIFT_THRESHOLD）、
      co_purchase_rate = 0.05（>CORATE_THRESHOLD=0.045）→ フラグ False。
    """
    source = _source(
        {"A": 0.1, "B": 0.1},
        [{"cat_mid_a": "A", "cat_mid_b": "B", "co_support": 0.05}],
    )

    rows = compute_metrics(source)

    assert rows[0]["lift"] == pytest.approx(5.0)
    assert rows[0]["co_purchase_rate"] == pytest.approx(0.05)
    assert rows[0]["high_lift_low_corate"] is False


def test_high_lift_low_corate_boundary_values_are_inclusive():
    """(2) 境界値: lift==LIFT_THRESHOLD かつ co_purchase_rate==CORATE_THRESHOLD ならTrue（両方 <=/>= が閾値含む）。

    手計算: support_A=support_B=1.0 とし、co_support=CORATE_THRESHOLD=0.045 のとき
      lift = 0.045 / (1.0*1.0) = 0.045 では閾値に届かないため、support を調整する。
      lift をちょうど LIFT_THRESHOLD=2.0 に、co_purchase_rate をちょうど
      CORATE_THRESHOLD=0.045 にするため、support_A=support_B=x を
      co_support = 2.0 * x^2 = 0.045 → x = sqrt(0.0225) = 0.15 とする。
    """
    x = 0.15
    co_support = LIFT_THRESHOLD * x * x  # = 0.045 = CORATE_THRESHOLD ちょうど
    assert co_support == pytest.approx(CORATE_THRESHOLD)

    source = _source(
        {"A": x, "B": x},
        [{"cat_mid_a": "A", "cat_mid_b": "B", "co_support": co_support}],
    )

    rows = compute_metrics(source)

    assert rows[0]["lift"] == pytest.approx(LIFT_THRESHOLD)
    assert rows[0]["co_purchase_rate"] == pytest.approx(CORATE_THRESHOLD)
    assert rows[0]["high_lift_low_corate"] is True  # 境界は両方とも含む(<=, >=)


def test_high_lift_low_corate_boundary_just_below_lift_threshold_is_false():
    """(2) lift が閾値をわずかに下回る（丸め後 1.99）と False になること。"""
    # lift = co_support / (support_A*support_B) が丸め後 1.99 になるよう設計。
    source = _source(
        {"A": 0.1, "B": 0.1},
        [{"cat_mid_a": "A", "cat_mid_b": "B", "co_support": 0.0199}],
    )

    rows = compute_metrics(source)

    assert rows[0]["lift"] == pytest.approx(1.99)
    assert rows[0]["high_lift_low_corate"] is False


def test_reproducible_same_input_yields_same_output():
    """(3) 同一入力を2回計算しても、バイト単位で同一の出力になること（再現性）。"""
    source = _source(
        {"A": 0.23, "B": 0.31, "C": 0.17},
        [
            {"cat_mid_a": "A", "cat_mid_b": "B", "co_support": 0.05},
            {"cat_mid_a": "B", "cat_mid_b": "C", "co_support": 0.02},
        ],
    )

    rows_1 = compute_metrics(source)
    rows_2 = compute_metrics(source)

    assert rows_1 == rows_2
    assert json.dumps(rows_1, ensure_ascii=False) == json.dumps(rows_2, ensure_ascii=False)


def test_unknown_cat_mid_raises_clear_error():
    """未知の中分類を参照するペアは、サイレントに無視せず例外を送出すること。"""
    source = _source(
        {"A": 0.5},
        [{"cat_mid_a": "A", "cat_mid_b": "DOES-NOT-EXIST", "co_support": 0.1}],
    )

    with pytest.raises(ValueError):
        compute_metrics(source)


def test_output_schema_matches_existing_co_purchase_columns():
    """(4) 出力の列が既存 co_purchase.json のスキーマ（cat_mid_a/b 等）と一致すること。"""
    source = _source(
        {"A": 0.5, "B": 0.4},
        [{"cat_mid_a": "A", "cat_mid_b": "B", "co_support": 0.1}],
    )

    rows = compute_metrics(source)

    expected_columns = {
        "cat_mid_a",
        "cat_mid_b",
        "co_purchase_rate",
        "support",
        "confidence",
        "lift",
        "high_lift_low_corate",
    }
    assert set(rows[0].keys()) == expected_columns


def test_run_generates_file_referencing_only_existing_product_categories(tmp_path):
    """(5) 参照整合: run() が生成した co_purchase.json の cat_mid が products.json に実在すること。

    実データの `data/co_purchase_source.json` を入力に、一時ディレクトリへ生成して検証する
    （本番の data/co_purchase.json を書き換えずに検証するため tmp_path を使う）。
    """
    from dataio import DEFAULT_DATA_DIR

    real_source_path = DEFAULT_DATA_DIR / "co_purchase_source.json"
    (tmp_path / "co_purchase_source.json").write_text(
        real_source_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    summary = run(data_dir=tmp_path)

    assert summary["generated"] > 0
    assert summary["high_lift_low_corate"] >= 1

    generated = json.loads((tmp_path / "co_purchase.json").read_text(encoding="utf-8"))
    assert len(generated) == summary["generated"]

    products = load_json_list("products.json")  # 本番 data/ から実商品マスタを読む
    cat_mids = {p["cat_mid"] for p in products}

    for row in generated:
        assert row["cat_mid_a"] in cat_mids, f"未知の中分類: {row['cat_mid_a']}"
        assert row["cat_mid_b"] in cat_mids, f"未知の中分類: {row['cat_mid_b']}"
