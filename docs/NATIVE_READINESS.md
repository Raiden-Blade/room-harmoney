# ネイティブアプリ化 移行readiness（フェーズ3-C）

要件定義書 9章「拡張性」（将来のネイティブアプリ化を見据えロジック/データをUIから分離）・
2章（PWA）・13章 フェーズ3 に基づき、既存の Web 実装（PWA）を Capacitor で包んで
ネイティブアプリ（Android/iOS）へ移行するための **readiness評価** と **雛形設定** をまとめる。

**本チャンクの到達点**: 「Webビルドを包む Capacitor 設定・依存・スクリプトの整備」までであり、
**実機ビルド・実機/エミュレータでのE2Eは実施していない**（後述「本環境の制約」を参照）。

## 1. 現状構成の監査 — UI / ロジック / データの分離

ネイティブアプリ化の可否は「UIを差し替えてもロジック・データ層が無傷で再利用できるか」に
懸かる。既存実装を監査した結果、以下の3層分離が既にできており、Capacitorによる
「Webをそのまま包む」方式・将来の段階的ネイティブ化のいずれにも対応できる状態にある。

| 層 | 実体 | UIからの独立度 |
|---|---|---|
| ロジック層（推薦） | `backend/recommender/`（`hybrid.py`, `personalized.py`）+ `backend/batch/lift_batch.py` | フロントUIに一切依存しない純Pythonモジュール。`RecommenderInterface` 相当の差し替え可能設計（DECISIONS #2）。単体テスト `backend/tests/unit/test_recommender.py`, `test_personalized.py` で直接検証されている＝UIを介さずロジック単体が動く証拠。 |
| ロジック層（経路探索） | `backend/routing/graph.py` | networkx グラフを直接操作する純Pythonモジュール。`backend/tests/unit/test_routing.py` がUIを介さず最短経路・巡回順を検証。 |
| データ層 | `backend/app/repositories.py`, `backend/app/store.py`, `data/` 配下のJSON/SQLite | APIルータ（`backend/app/routers/*.py`）経由でのみロジック層・UIに公開。生データの形式（SQLite/JSON）はUI側から不可視。 |
| API境界 | `backend/app/routers/*.py`（`products`, `recommendations`, `route`, `coordinates`, `session`, `qr`, `store_map`, `events`, `admin`） | `docs/openapi.json` として型定義がエクスポートされ、フロントは `openapi-typescript` 生成の `frontend/src/api/schema.ts` を介した**型付きHTTPクライアント** `frontend/src/api/client.ts` のみでバックエンドと通信する。UIコンポーネント（`frontend/src/pages/*.tsx`, `frontend/src/components/*.tsx`）はこのクライアント関数（`getRecommendations`, `getRoute`, `getProduct` 等）を呼ぶだけで、推薦アルゴリズムや経路探索アルゴリズムの実装詳細を一切知らない。 |
| フロント内部のUI/ロジック分離 | `frontend/src/deeplink.ts`, `frontend/src/routeFloorTransfers.ts` | DOM/Reactフックに依存しない純関数として実装され、`frontend/src/__tests__/` で単体テストされている。UIコンポーネントから呼ばれるが、UIそのものではない。 |

**結論**: ロジック（推薦・経路探索）とデータはバックエンドAPIの内側に閉じており、フロントは
「型付きAPIクライアント＋UIコンポーネント」のみで構成されている。したがって：

- **方式A（Capacitorで包む＝本チャンクの対象）**: フロントの`dist/`（Vite本番ビルド）をそのまま
  ネイティブWebViewに載せるだけでよく、バックエンド・ロジック層は無改造で共有できる。
- **方式B（将来・機能単位のネイティブ化）**: QR読取・位置情報・ディープリンクなど
  「ブラウザAPI依存」の箇所だけを対応するCapacitorプラグインに差し替えれば足り、
  推薦・経路探索・データ取得のロジックはAPI境界の内側にあるため変更不要。

いずれの方式でも「ロジック/データをUIから分離」という9章の要件を満たせる構成になっている。

## 2. 中核機能のネイティブ移行方針

### 2.1 QRコード読取（S1 `ScanPage`、7章・4章）

- 現状: `frontend/src/components/QrCameraScanner.tsx` が `html5-qrcode`（`getUserMedia`）で
  ブラウザのカメラAPIを直接使用。
- ネイティブ移行案: `@capacitor/camera`（本チャンクで依存追加済み）または
  Capacitor Community の BarcodeScanner系プラグインへの置換を想定。ネイティブでは
  OS標準のカメラパーミッションフローとネイティブデコーダを使うことで読取速度・省電力の
  改善が見込める。
- **Web版（PWA）は現状維持**: `html5-qrcode` はそのまま残し、Capacitor WebView上では
  `Capacitor.isNativePlatform()` 等で分岐して切り替える設計とする（実装はスコープ外、
  方針のみ）。QRのフォールバック（URL直リンク、DECISIONS #6）はネイティブでも
  ディープリンク（2.3節）でそのまま機能する。

### 2.2 位置情報・ジオフェンス（フェーズ3-B `backend/app/visit.py`）

- 現状: フェーズ3-B（`gate-P3B-20260807.md` GREEN）は **バックエンド側**の来店判定拡張
  （`GeofenceVerifier`/`WifiVerifier`、`backend/app/visit.py`）であり、`location`/`wifi_ssid`
  は `POST /api/session` のオプション入力として受け取る設計。現時点のフロント
  （`frontend/src`）はこれらのフィールドを送信する実装を持たない（バックエンドのみで
  完結、DECISIONS #7「既定はQR、Wi-Fi/ジオフェンスは拡張余地」）。
- ネイティブ移行案: 将来フロントが位置情報を収集して送信する場合、Web版は
  `navigator.geolocation`、ネイティブ版は `@capacitor/geolocation`（本チャンクで依存追加済み）
  を使う。両者とも「緯度経度を取得してAPIに渡す」だけのアダプタで、判定ロジック
  （`GeofenceVerifier`）はバックエンドに閉じているため、位置情報の取得元（Web/ネイティブ）が
  変わってもサーバ側ロジックは無改造で共有できる。
- プライバシー（P3-Bで確認済み: `events`テーブルには位置情報を保存しない）は取得元に依らず
  バックエンド側のスキーマ制約（`events`テーブルに位置情報カラム無し）で担保されており、
  ネイティブ化してもこの保証は変わらない。

### 2.3 ディープリンク（4.4章、`frontend/src/deeplink.ts`）

- 現状: `parseInboundDeepLink`/`buildRoutePath`/`buildChatbotUrl` はDOM非依存の純関数。
  Web版では `ScanPage`（`frontend/src/pages/ScanPage.tsx`）が `react-router-dom` の
  `useSearchParams()` で取得した `URLSearchParams` をこれらの関数に渡す構成
  （本チャンクでは変更していない）。
- ネイティブ移行案: `@capacitor/app`（本チャンクで依存追加済み）の `App.addListener('appUrlOpen', ...)`
  でカスタムURLスキーム（例 `roomharmony://...`）やUniversal Links/App Linksの起動URLを
  受け取り、そのURLの `search` 部分を同じ `parseInboundDeepLink(new URL(url).searchParams)` に
  渡せば、**既存の純関数をそのまま再利用**できる。パラメータ仕様（`product_id`/`coordinate_id`/
  `to_product`/`screen`）はWeb/ネイティブで共通のまま変更不要。
- outbound側（チャットボットへの導線、`buildChatbotUrl`）は、ネイティブでチャットボットも
  別ネイティブアプリ/Webである場合、OSのURL起動（`window.open` 相当のネイティブAPI）に
  差し替える想定。ロジック（URL組み立て）自体は共通関数のまま。

### 2.4 API接続（17章、`frontend/src/api/client.ts`）

- 現状: `API_BASE_URL` は `VITE_API_BASE_URL`（`.env`）から取得し既定値
  `http://localhost:8000`（`frontend/src/api/client.ts` 21-22行目）。通信は標準 `fetch` のみで
  ブラウザ/WebView双方で動作する（Capacitor WebViewは`fetch`をサポート）。
- 本番ネイティブビルドでは `VITE_API_BASE_URL` をビルド時に本番APIのHTTPSエンドポイントへ
  設定する（Capacitorはビルド時に環境変数を埋め込む点はWeb版と同じ、`.env.production`等で
  切り替え）。
- 留意点:
  - **HTTPS必須**: iOSのATS（App Transport Security）はデフォルトで平文HTTP通信を拒否する。
    本番APIはHTTPS化が前提（開発時のみ`NSAppTransportSecurity`例外設定やCapacitorの
    `server.cleartext`で緩和可能、`capacitor.config.ts`にコメントで記載済み）。
  - **CORS**: ネイティブWebViewからのリクエストはOriginが`capacitor://localhost`
    （iOS）/`http://localhost`（Android既定）になるため、バックエンドのCORS許可オリジンに
    ネイティブ用オリジンの追加が必要になる場合がある（`backend/app/main.py` のCORS設定を
    実機ビルド時に見直すこと。本チャンクではbackend側は変更していない）。

## 3. Capacitorの雛形設定（本チャンクで追加したもの）

- `frontend/capacitor.config.ts`: `appId: "jp.co.nitori.roomharmony"`（ダミー値、実運用時に
  ニトリ側の正式IDへ差し替え）、`appName: "Room Harmony"`、`webDir: "dist"`（既存Viteビルドの
  出力先そのまま）。開発時にネイティブシェルからdevサーバへ直接接続するための`server`設定は
  コメントアウトで用意（デバッグ専用、既定では無効）。
- 依存追加（`frontend/package.json`）:
  - `dependencies`: `@capacitor/core`, `@capacitor/camera`, `@capacitor/geolocation`,
    `@capacitor/app`
  - `devDependencies`: `@capacitor/cli`
- npm scripts追加: `cap:sync`（`cap sync`）, `cap:add:android`（`cap add android`）,
  `cap:add:ios`（`cap add ios`）。**いずれも本チャンクでは実行していない**（4節参照）。
- `.gitignore`（リポジトリルート）に `frontend/android/`, `frontend/ios/` を追記済み
  （ネイティブプロジェクトフォルダは将来 `cap add` で生成された際に誤ってコミットしないため。
  現時点では未生成なので実体は存在しない）。

## 4. 本環境の制約（実施できなかったこと）

本開発環境には **Xcode（macOS専用）・Android Studio・Android/iOS実機・エミュレータが
存在しない**。そのため以下は本チャンクでは実行していない（環境制約であり、設定・依存・
ドキュメント整備というスコープの範囲では対応不要と判断）:

- `npx cap add android` / `npx cap add ios`（ネイティブプロジェクトフォルダの生成。
  Android SDK / Xcode Command Line Toolsが必須）
- `npx cap sync`（ネイティブプロジェクトへのWebアセット・プラグインコピー。生成された
  ネイティブプロジェクトが前提のため、上記が未実行だと対象が無い）
- ネイティブアプリの実機/エミュレータビルド、実機E2E、ストア申請関連の検証

代わりに本チャンクで実施・確認したこと:

- `npm install`（Capacitor関連パッケージの依存解決）
- `npx cap --version`（CLI自体が正常に動作することの確認、`8.5.0`）
- `npm run build`（既存Webビルドが `capacitor.config.ts` 追加後も無回帰で成功、`dist/`生成）
- `npm run test`（vitest、既存49件が無回帰でPASS）
- backend側の無回帰確認（`pytest`、既存152件PASS。backendは本チャンクで無改造）

## 5. 実機ビルド手順（別環境向け・参考）

Xcode/Android Studioが利用可能な環境で以下を実行する想定手順:

```bash
# 1. Webアセットをビルド（frontend/dist を生成）
cd frontend
npm install
npm run build

# 2. ネイティブプロジェクトを生成（初回のみ。本チャンクでは未実行）
npx cap add android   # Android Studio / Android SDK が必要
npx cap add ios       # Xcode（macOS）が必要

# 3. Web資産・プラグインをネイティブプロジェクトへ同期
#    （Webコードを変更するたびに実行）
npm run build && npx cap sync

# 4. ネイティブIDEで開いて実機/エミュレータ実行
npx cap open android   # Android Studio が起動
npx cap open ios       # Xcode が起動（macOSのみ）
```

必要な環境: Android は Android Studio + Android SDK（API level はCapacitor 8系の
サポート範囲に準拠）、iOS は macOS + Xcode + CocoaPods。詳細はCapacitor公式ドキュメントの
プラットフォーム要件に従う。

## 6. 段階的移行の推奨

1. **第一段階（本チャンクの対象）**: Capacitorで既存PWAをそのまま包む。UI・APIクライアント・
   バックエンドは無改造のまま、ネイティブの配布形態（App Store/Google Play）だけを得る。
   既存資産（`frontend/dist`、`backend`一式）を最大限再利用できるため移行コストが最小。
2. **第二段階**: 実際にネイティブ実行してみて体験上の課題が出た機能（QR読取の速度、
   位置情報の精度、バックグラウンド動作など）だけを対応するCapacitorプラグインへ
   個別に置換する（2章参照）。API境界・推薦/経路探索ロジックは変更不要なため、
   影響範囲をフロントのアダプタ層に限定できる。
3. **判断基準**: 各機能の置換要否は「Web版の体験で十分か」で判断し、置換する場合も
   `Capacitor.isNativePlatform()` 分岐でWeb/ネイティブ両対応を維持し、PWAとしての
   提供を止めない（2章 PWA要件を継続担保）。

## 7. 参照

- 要件定義書 9章（拡張性）, 2章（PWA）, 13章（フェーズ3）
- `docs/DECISIONS.md` #2（推薦ロジック差し替え可能性）, #6（QRフォールバック）,
  #7（来店判定モードの差し替え可能性）
- `harness/reports/gate-P3A-20260807.md`, `harness/reports/gate-P3B-20260807.md`
  （直近フェーズのゲート結果、本チャンクの前提として参照）
- `frontend/capacitor.config.ts`, `frontend/package.json`
