"""リフト算出バッチ本実装（フェーズ2-A / 要件5.1・8.2「バッチで前計算」）。

DECISIONS.md #2 の前提（中分類レベルの併売率を基本として扱い、色スコアは使わない・
トランザクション生データは無い）に従い、`data/co_purchase_source.json`（中分類ごとの
単体支持度 `support` と、中分類ペアごとの共起支持度 `co_support` という「素の集計」）
から、`data/co_purchase.json`（既存スキーマ: cat_mid_a, cat_mid_b, co_purchase_rate,
support, confidence, lift, high_lift_low_corate）を **生成物として** 再現可能に算出する。

算出式（各ペア A→B。方向は cat_mid_a → cat_mid_b）:
    support     = co_support                              … P(A∩B) そのもの
    confidence  = co_support / support_A                  … P(B|A)
    lift        = co_support / (support_A * support_B)
    co_purchase_rate = co_support                          … 併売率の基本値（support と同値）
    high_lift_low_corate = (lift >= LIFT_THRESHOLD) and (co_purchase_rate <= CORATE_THRESHOLD)

`co_purchase_source.json` が実データ（POS由来の中分類集計）に差し替われば、本バッチを
再実行するだけで `co_purchase.json` が更新される。`RecommenderInterface` 実装
（`recommender/hybrid.py`）は生成後の `co_purchase.json` の形（cat_mid_a/b, lift,
high_lift_low_corate）にのみ依存するため、算出方法を差し替えても実装への影響はない
（`data/README.md` co_purchase.json 節も参照）。

責務分離：
- `compute_metrics()` … 純粋関数。入出力ファイルに触れず、テスト容易性を担保する。
- `load_source()` / `write_output()` … I/O。
- `run()` … 上記を束ねるオーケストレーション（CLI からも呼ばれる）。

CLI:
    cd backend
    .venv\\Scripts\\python.exe -m batch.lift_batch
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from dataio import DEFAULT_DATA_DIR

SOURCE_FILENAME = "co_purchase_source.json"
OUTPUT_FILENAME = "co_purchase.json"

# 「リフトは高いのに現状の併売率が低い」＝伸びしろペアの判定閾値（外出し・調整可能）。
# data/README.md の既存サンプルデータ記述（lift>=2.0 かつ support<=0.045）と整合させる。
LIFT_THRESHOLD: float = 2.0
CORATE_THRESHOLD: float = 0.045

# 再現性のための丸め桁数（浮動小数の桁を固定し、同一入力→同一出力を保証する）。
SUPPORT_ROUND_DIGITS = 4
CONFIDENCE_ROUND_DIGITS = 3
LIFT_ROUND_DIGITS = 2


def compute_metrics(source: dict[str, Any]) -> list[dict[str, Any]]:
    """`co_purchase_source.json` 相当の辞書から co_purchase.json の行リストを算出する（純粋関数）。

    Args:
        source: `{"category_support": [{"cat_mid": str, "support": float}, ...],
                  "co_purchases": [{"cat_mid_a": str, "cat_mid_b": str, "co_support": float}, ...]}`

    Returns:
        cat_mid_a, cat_mid_b, co_purchase_rate, support, confidence, lift,
        high_lift_low_corate を持つ行のリスト（`co_purchases` の入力順を保つ）。

    Raises:
        ValueError: ペアが参照する中分類が `category_support` に無い、または
            該当中分類の単体支持度が 0 以下（confidence/lift がゼロ除算になる）の場合。
    """
    category_support: dict[str, float] = {}
    for entry in source.get("category_support", []):
        category_support[entry["cat_mid"]] = float(entry["support"])

    rows: list[dict[str, Any]] = []
    for pair in source.get("co_purchases", []):
        cat_mid_a = pair["cat_mid_a"]
        cat_mid_b = pair["cat_mid_b"]

        if cat_mid_a not in category_support:
            raise ValueError(f"未知の中分類が co_purchases に含まれています: {cat_mid_a!r}")
        if cat_mid_b not in category_support:
            raise ValueError(f"未知の中分類が co_purchases に含まれています: {cat_mid_b!r}")

        support_a = category_support[cat_mid_a]
        support_b = category_support[cat_mid_b]
        if support_a <= 0 or support_b <= 0:
            raise ValueError(
                f"中分類の単体支持度は正の値である必要があります: "
                f"{cat_mid_a}={support_a}, {cat_mid_b}={support_b}"
            )

        co_support = float(pair["co_support"])

        # 明示式（モジュールdocstring参照）。confidence/lift の方向は cat_mid_a → cat_mid_b。
        support = co_support
        confidence = co_support / support_a
        lift = co_support / (support_a * support_b)
        co_purchase_rate = co_support

        support_rounded = round(support, SUPPORT_ROUND_DIGITS)
        co_purchase_rate_rounded = round(co_purchase_rate, SUPPORT_ROUND_DIGITS)
        confidence_rounded = round(confidence, CONFIDENCE_ROUND_DIGITS)
        lift_rounded = round(lift, LIFT_ROUND_DIGITS)

        high_lift_low_corate = (
            lift_rounded >= LIFT_THRESHOLD and co_purchase_rate_rounded <= CORATE_THRESHOLD
        )

        rows.append(
            {
                "cat_mid_a": cat_mid_a,
                "cat_mid_b": cat_mid_b,
                "co_purchase_rate": co_purchase_rate_rounded,
                "support": support_rounded,
                "confidence": confidence_rounded,
                "lift": lift_rounded,
                "high_lift_low_corate": high_lift_low_corate,
            }
        )

    return rows


def load_source(data_dir: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    """`co_purchase_source.json` を読み込む。

    バッチの明示的な入力であるため、`dataio.load_json_*` の「欠損時は空にフォールバック」
    とは異なり、欠損・不正JSONの場合は明確な例外を送出する（サイレントに空の
    co_purchase.json を生成してしまう事故を防ぐため）。
    """
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    path = base / SOURCE_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {path}")
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} はオブジェクト（dict）である必要があります")
    return data


def write_output(rows: list[dict[str, Any]], data_dir: Optional[Union[str, Path]] = None) -> Path:
    """算出結果を `co_purchase.json` として上書き生成する。"""
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    path = base / OUTPUT_FILENAME
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run(data_dir: Optional[Union[str, Path]] = None) -> dict[str, int]:
    """バッチ本体：読み込み→算出→書き出しを行い、件数サマリを返す。"""
    source = load_source(data_dir=data_dir)
    rows = compute_metrics(source)
    write_output(rows, data_dir=data_dir)
    high_lift_low_corate_count = sum(1 for row in rows if row["high_lift_low_corate"])
    return {"generated": len(rows), "high_lift_low_corate": high_lift_low_corate_count}


def main() -> None:
    summary = run()
    print(
        f"co_purchase.json を生成しました: {summary['generated']} 件"
        f"（うち高リフト×低併売率＝伸びしろペア: {summary['high_lift_low_corate']} 件）"
    )


if __name__ == "__main__":
    main()
