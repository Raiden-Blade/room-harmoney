# Room Harmony

来店客向けWebアプリ（レスポンシブ／PWA）。店内QRのスキャンを起点に、**関連商品提示・コーディネート提案・店内簡易ルート案内**を行い、同じ空間の商品の併売を促す。
要件は `docs/DESIGN.md`（全体設計）・`docs/DECISIONS.md`（発注者確認済みの確定事項）・`docs/HARNESS.md`（開発ハーネス）を参照。

> ステータス: **フェーズ1 MVP 実装・検証済み**（G1 推薦/経路単体 → G2 API結合 → G3 フロント → G4 E2Eハッピーパス まで、独立QAゲートを通過）。各ゲートの合否・証跡は `harness/reports/` と `harness/evidence/` を参照。

---

## 1. 前提環境

- OS: Windows（PowerShell / Git Bash いずれでも可）
- Python: **`py` ランチャ経由**で実行（`python` は Windows Store のスタブで動作しない環境がある）。確認: `py --version`（3.13系）
- Node.js: v22 系 / npm 10 系。確認: `node -v` / `npm -v`
- git: 2.x

---

## 2. リポジトリ構成

```
room-harmony/
├─ frontend/         # TypeScript + React（Vite, PWA）。QR読取・SVG地図/ルート・5画面・計測
│  ├─ src/api/       # OpenAPIからの型・fetchクライアント
│  ├─ src/pages/     # S1 Scan / S2 Product / S3 Coordinate / S4 Route
│  ├─ src/components/# FloorMap(SVG) / VisitLock / ChatbotLink 等
│  ├─ src/hooks/     # useEventLog（計測）
│  └─ e2e/           # Playwright E2E（G4）
├─ backend/          # Python + FastAPI
│  ├─ app/           # API層（main.py, routers/, dependencies.py, store.py, experiment.py, errors.py）
│  ├─ recommender/   # 中分類併売率→リフト近似＋ハイブリッド（RecommenderInterface / HybridRecommender）
│  ├─ routing/       # ウェイポイント・グラフ最短経路（networkx, 4フロア・階段/EV接続）
│  ├─ dataio/        # data/*.json ローダ（欠損時フォールバック）
│  ├─ scripts/       # export_openapi.py（docs/openapi.json 出力）
│  └─ tests/         # unit（G1）/ integration（G2）
├─ data/             # サンプルデータ（products/co_purchase/coordinates/store_map/qr_codes/aggregates ほか）
├─ docs/             # DESIGN / DECISIONS / HARNESS / openapi.json
├─ harness/          # QAゲートのレポート・証跡
├─ .env.example
└─ README.md
```

---

## 3. 環境変数（`.env.example`）

`.env.example` をコピーして `.env` を作成し値を設定する。秘匿値は `.env` に直書きし、コミットしないこと（`.gitignore` 済み）。

| 変数 | 用途 |
|---|---|
| `DATABASE_URL` | セッション/イベントログの保存先。開発は SQLite（既定 `sqlite:///./data/room_harmony.db`）。本番は PostgreSQL 等に差し替え |
| `CHATBOT_BASE_URL` | 既存チャットボットの連携先URL（相互リンク・ディープリンク） |
| `STORE_ID` | 対象店舗ID（サンプルは目黒通り店ベースの4フロア、既定 `meguro-dori`） |
| `EXPERIMENT_GROUP_MODE` / `EXPERIMENT_GROUP_RATIO` | 実験群（A/B）割付の方式・比率（既定 random / 0.5） |
| `CORS_ALLOW_ORIGINS` | バックエンドCORS許可オリジン（カンマ区切り。既定に dev 5173 / preview 4173 を含む） |
| `VITE_API_BASE_URL` | フロントから参照するバックエンドAPIのベースURL（既定 `http://localhost:8000`） |
| `VITE_CHATBOT_BASE_URL` | フロントからのチャットボット導線URL（未設定でもダミー既定値で動作） |

```powershell
Copy-Item .env.example .env
```

---

## 4. セットアップ・起動

### 4.1 バックエンド（Python + FastAPI）

```powershell
cd backend
py -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt

# 開発サーバ起動（http://localhost:8000）
.venv\Scripts\python -m uvicorn app.main:app --reload
```

動作確認: `http://localhost:8000/health` が `{"status":"ok"}` を返す。API仕様は起動後 `http://localhost:8000/docs`（Swagger UI）、または `docs/openapi.json`。

サンプルデータは `data/*.json` をそのまま参照する（別途の投入作業は不要）。OpenAPIスキーマを再生成する場合:

```powershell
cd backend
.venv\Scripts\python scripts\export_openapi.py   # docs/openapi.json を出力
```

**リフト算出バッチ（フェーズ2-A）**：`data/co_purchase.json` は手書きではなく、
`data/co_purchase_source.json`（中分類の単体支持度・共起支持度という「素の集計」。実データ差し替え口）
から以下のコマンドで再現可能に生成する（詳細・算出式は `data/README.md`）:

```powershell
cd backend
.venv\Scripts\python -m batch.lift_batch
```

### 4.2 フロントエンド（TypeScript + React / Vite）

```powershell
cd frontend
npm install
npm run gen:api      # docs/openapi.json から src/api/schema.ts を生成
npm run dev          # http://localhost:5173
```

本番ビルド／プレビュー:

```powershell
npm run build
npm run preview      # http://localhost:4173
```

---

## 5. 一連の体験を再現する（カメラ不要のURL直リンク）

実カメラが無くても、QRに紐づくURL直リンクで同一フローに到達できる（要件4.1のフォールバック）。
backend（8000）と frontend（dev 5173 もしくは preview 4173）を起動した状態で、ブラウザで次を開く:

```
http://localhost:5173/s/QR-PRODUCT-P001
```

1. **S1 スキャン**: `QR-PRODUCT-P001` を解決してセッション開始（`experiment_group` 割付、`session_start`/`qr_scan` 記録）
2. **S2 商品詳細**: 商品情報＋**関連商品（リフト順）**＋この商品を使ったコーディネートを表示
3. 関連の「場所を見る」→ **S4 マップ・ルート**（起点→目的商品の経路をSVGに描画、経由サブ通路表示）／コーデ→ **S3 コーデ詳細**（完成イメージ・構成商品・合計金額目安）
4. 各操作は効果ログとして記録される（`related_view`/`route_view`/`coordinate_view` 等、すべて `experiment_group` 付き）

- 入口QR例: `http://localhost:5173/s/QR-ENTRANCE-001`
- 実在の商品ID/QR/コーデIDは `data/products.json` `data/qr_codes.json` `data/coordinates.json` を参照
- **来店ロック**: 有効なQR起点セッションが無い状態で `/route` 等の中核画面に直接アクセスすると、機能がロックされQR読取を促す

---

## 6. テスト実行手順

### 6.1 バックエンド（単体 G1 / 結合 G2）

```powershell
cd backend
.venv\Scripts\python -m pytest tests\unit -v          # G1: 推薦・経路・データ整合の単体テスト
.venv\Scripts\python -m pytest tests\integration -v   # G2: API結合テスト（/health スモーク含む）
.venv\Scripts\python -m pytest tests -v                # まとめて実行
```

### 6.2 フロントエンド（コンポーネント/結合）

```powershell
cd frontend
npm run test         # vitest（画面描画・イベント発火・来店ロック・SVGルート描画）
```

### 6.3 E2E（G4・Playwright）

```powershell
cd frontend
npm run test:e2e     # Playwright（URL直リンク経由のハッピーパス）
```

> 注意: E2Eは Chromium を起動する。**本リポジトリを構築した端末では Windows の SxS 構成不具合により Chromium が起動できず、スクリーンショットPNGは取得できなかった**（アプリの不具合ではなく端末固有の問題）。G4はDOM/ネットワーク実レスポンス＋DB直接検証で合格を確認済み。画面キャプチャが必要な場合は、Chromium が起動できる別環境で `npm run test:e2e` を実行すればPNG証跡が得られる。

---

## 7. 開発ハーネス・ゲート

実装エージェントとQAエージェントを分離したテストゲート方式（`docs/HARNESS.md`）で開発。合否・証跡は `harness/reports/`・`harness/evidence/` に記録。

| ゲート | 対象 | コマンド | レポート |
|---|---|---|---|
| G1 | 推薦・経路（単体） | `cd backend && py -m pytest tests/unit -v` | `harness/reports/gate-G1-*.md` |
| G2 | API（結合） | `cd backend && py -m pytest tests/integration -v` | `harness/reports/gate-G2-*.md` |
| G3 | フロント（ビルド/コンポーネント） | `cd frontend && npm run build && npm run test` | `harness/reports/gate-G3-*.md` |
| G4 | E2Eハッピーパス | `cd frontend && npm run test:e2e` | `harness/reports/gate-G4-*.md` |

---

## 8. 現時点のステータス（フェーズ1 MVP）

- [x] backend: FastAPI、17章の8エンドポイント、来店ロック、experiment_group割付、イベントログ（SQLite）
- [x] recommender: 中分類併売率→支持度/信頼度/リフト近似、ハイブリッド並び（重みは外出し・A/B調整可）
- [x] routing: 4フロアのウェイポイント最短経路・巡回順（networkx）
- [x] frontend: S1〜S5画面、QR読取（カメラ＋URL直リンクfallback）、SVGフロアマップ/ルート、PWA、計測
- [x] サンプルデータ一式（`data/`、実データ差し替え可能な構造）
- [x] テスト: 単体（G1）・結合（G2）・コンポーネント（G3）・E2E（G4）
- [x] フェーズ2-A: リフト算出バッチ本実装（`backend/batch/lift_batch.py`。`data/co_purchase_source.json` → `data/co_purchase.json` を再現可能に生成、単体テスト `backend/tests/unit/test_lift_batch.py`）
- [ ] フェーズ2（本番強化・残り）: A/B×KPI突合ダッシュボード、チャットボット双方向ディープリンクの拡張 ほか（`docs/DESIGN.md`・要件13章参照）
</content>
