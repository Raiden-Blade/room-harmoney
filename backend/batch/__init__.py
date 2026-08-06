"""リフト算出バッチ（フェーズ2-A / 要件5.1・8.2「バッチで前計算」）。

`co_purchase_source.json`（上流の中分類集計。実データ差し替え口）から
`co_purchase.json`（中分類ペアの support/confidence/lift/high_lift_low_corate）を
再現可能に生成する。実行は `backend/batch/lift_batch.py` を参照。
"""
