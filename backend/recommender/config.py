"""ハイブリッド推薦の重み設定（5.3章「重みは設定値として外出しし、A/Bで調整可能にする」）。

`HybridRecommender.recommend(product_id, weights=...)` の引数でデフォルト値を
上書きできる。A/Bテストの実験群ごとに異なる重みセットを渡す用途を想定。
"""
from typing import Final

DEFAULT_WEIGHTS: Final[dict[str, float]] = {
    # データドリブン（中分類リフト）のスコアへの寄与度
    "lift_weight": 1.0,
    # キュレーション適合度（起点商品と同じコーディネートに含まれるか）のスコアへの寄与度
    "coordinate_weight": 0.5,
    # 「リフト高×併売率低（伸びしろ）」フラグが立った中分類ペアを優先的に押し上げる倍率。
    # lift 項に乗算する（例: lift=2.0 で boost=1.15 なら score へは 2.3 相当寄与）。
    "high_lift_low_corate_boost": 1.15,
}
