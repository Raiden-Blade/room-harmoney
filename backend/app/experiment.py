"""A/B実験群割付（10章「experiment_group」/ DECISIONS.md #7 関連）。

`.env` の `EXPERIMENT_GROUP_MODE` / `EXPERIMENT_GROUP_RATIO` を尊重しつつ、
テストで決定的に検証できるよう乱数生成器（`random.Random`）を注入可能にする
（シード固定でユニットテスト/結合テストが常に同じ結果になるようにするため）。

前提（未確定事項寄りの実装判断・コメントで明記）:
要件定義書 10章は「Room Harmony利用群 / 非利用群」という2群のみを定義しており、
具体的な値の命名までは規定していない。ここでは `treatment`（利用群）/ `control`
（非利用群）という一般的なA/Bテスト用語を採用する。
"""
from __future__ import annotations

import random
from typing import Optional

TREATMENT = "treatment"
CONTROL = "control"


class ExperimentAssigner:
    """セッション作成時に呼ばれる実験群割付ロジック。"""

    def __init__(
        self,
        mode: str = "random",
        ratio: float = 0.5,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.mode = mode
        self.ratio = ratio
        # rng を外部から注入できるようにし、結合テストではシード固定のインスタンスに
        # 差し替えることで割付結果を決定的に検証できるようにする。
        self._rng = rng if rng is not None else random.Random()

    def assign(self) -> str:
        """`ratio` の確率で TREATMENT、それ以外は CONTROL を返す。

        現時点のMVPでは mode の値によらず ratio に基づくベルヌーイ割付を行う
        （mode="random" が既定・唯一の実装。将来 mode を増やす場合はここに分岐を追加する）。
        """
        return TREATMENT if self._rng.random() < self.ratio else CONTROL
