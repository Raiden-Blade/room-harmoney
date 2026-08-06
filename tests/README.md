# tests/

ルート直下の `tests/` は、リポジトリ横断のE2E（G4）シナリオ等、単一パッケージに属さないテストのための場所です。

各層固有のテストは以下に配置し、そちらで実行します（16章 リポジトリ構成 / HARNESS.md 6章）。

- 単体・結合テスト（Python）: `backend/tests/unit/`, `backend/tests/integration/`
  - 実行: `cd backend && py -m pytest tests/unit -v` / `py -m pytest tests/integration -v`
- E2E（実ブラウザ / Playwright、フロントが動く段階で追加）: `frontend/` 配下（`npm run test:e2e`）

このディレクトリ自体は、E2Eテスト（G4）実装時にPlaywrightの設定・シナリオファイルを置く想定です（現時点は雛形のみ、TODO）。
