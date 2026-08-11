"""テスト用の固定フィクスチャディレクトリ（段階A: `data/` からのテスト切り離し）。

`DATA_DIR` は `backend/tests/fixtures/data/`（本リファクタ時点の `data/*.json`
サンプルをそのままコピーしたもの。`.db` は含めない）を指す。`data/` を実データへ
差し替えても、このフィクスチャは変わらないため、参照しているテストは壊れない。

テストは以下のいずれかでこのディレクトリを参照する:
- `dataio.load_json_list` / `load_json_dict` 等を直接呼ぶ箇所: `data_dir=DATA_DIR` を渡す。
- FastAPI の `client` フィクスチャ経由（DI チェーン）: `backend/tests/conftest.py` が
  `RH_DATA_DIR` 環境変数をこのディレクトリに設定するため、`app.config.Settings.data_dir`
  経由で自動的にこちらを参照する。
"""
from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

__all__ = ["DATA_DIR"]
