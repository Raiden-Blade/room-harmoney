"""ルート conftest（段階A: テストをライブの `data/` から切り離すリファクタ）。

背景（コメントで理由を残す）:
この後 `data/` を実データ（約9,180件）へ差し替える予定のため、テストが
ライブの `data/*.json` を直接参照していると、差し替えのたびに件数・並び順・
価格等のアサーション（例: `products.json` は30〜50点、`P001` の価格は39,900円）が
壊れてしまう。そこで、テストは常に「サンプルの固定コピー」である
`backend/tests/fixtures/data/`（本リファクタ時点の `data/*.json` をそのままコピーした
もの。`.db` は含めない）を参照するようにする。

やり方:
1. `RH_DATA_DIR` 環境変数をフィクスチャディレクトリの絶対パスに設定する
   （このモジュールはどのテストモジュールよりも先にインポートされるため、
   `app.config.Settings.from_env()`／`app.dependencies` 経由でデータを読む
   FastAPI 依存関係チェーン（`get_product_repo` 等）はすべて自動的にフィクスチャを
   参照するようになる。`app/config.py` の `Settings.data_dir` 参照）。
2. `FIXTURES_DATA_DIR` を公開し、`dataio.load_json_list` 等を直接呼ぶテスト
   （`app` の DI チェーンを経由しない単体/結合テスト）が明示的にフィクスチャを
   指せるようにする。

本番/開発時は `RH_DATA_DIR` を設定しないため、この切り替えはテスト実行時のみに限定され、
アプリの既定の動作（`data/` 参照）は変わらない。
"""
from __future__ import annotations

import os

from tests.fixtures import DATA_DIR as FIXTURES_DATA_DIR

# conftest.py はどのテストモジュールよりも先にpytestがインポートするため、ここで
# 環境変数を設定すれば `app.main`（CORS設定のため import 時に `get_settings()` を
# 呼ぶ）を含め、以降のあらゆる `Settings.from_env()` 呼び出しがフィクスチャを見る。
os.environ.setdefault("RH_DATA_DIR", str(FIXTURES_DATA_DIR))
