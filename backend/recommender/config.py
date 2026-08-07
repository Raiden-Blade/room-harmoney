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

# フェーズ3-A（DECISIONS.md 改訂#5-A）: 会員購入履歴アフィニティのスコア倍率重み。
# `PersonalizedRecommender`（backend/recommender/personalized.py）が使用する。
#
#   score' = score_base * (1 + MEMBER_AFFINITY_WEIGHT * affinity_count(member, cat_mid))
#
# affinity_count は「会員がその中分類（related候補の cat_mid）を過去に買った回数」。
# 0.15 は「該当中分類を1回買っていれば15%増し、3回なら45%増し」というオーダー感で、
# base のリフト由来スコアを主信号として維持しつつ、僅差の順位を入れ替えられる程度の
# 強さに抑えた値（要件定義書には具体値の指定が無いため、5.3章「重みは設定値として
# 外出しし、A/Bで調整可能にする」方針に沿って設定値化し、暫定値として採用した前提を
# ここにコメントで残す）。呼び出し引数 `member_affinity_weight` で上書き可能。
MEMBER_AFFINITY_WEIGHT: Final[float] = 0.15
