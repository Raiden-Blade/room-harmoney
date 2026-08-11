# ゲートレポート FEAT-PCODE（商品番号による直接遷移） — 2026-08-09

- 検証者: rh-qa-reviewer（実装から独立。実装コードは一切変更していない）
- 対象機能: 商品番号（`LL-MM-SS-NNN`、数字9桁、ハイフン有無どちらも許容）による直接遷移
  - `backend/batch/product_codes.py`（採番バッチ）
  - `backend/app/routers/product_code.py`（`GET /api/product-code/{code}`）
  - `backend/app/repositories.py`（`normalize_product_code` / `ProductRepository.get_by_code`）
  - `frontend/src/pages/ScanPage.tsx`（手入力フォーム）
  - `frontend/src/pages/ProductPage.tsx`（商品番号表示）
  - `frontend/src/api/client.ts`（`resolveProductCode`）
- 対象状態: `data/products.json` / `data/qr_codes.json` は着手前から既に `product_code` 付与済み（実装エージェントが事前に一度採番バッチを実行した状態）。QAはこの状態を変更せず、採番バッチをQA自身でも隔離実行・再実行して再現性を検証した（詳細はG-1参照。最終的にリポジトリのdata/はQA着手前と完全一致することを確認済み）。
- 総合判定: **GREEN（G-1〜G-6 すべて PASS）**

## ゲート別 合否表

| ゲート | 内容 | 判定 | 証跡 |
|---|---|---|---|
| G-1 | 採番バッチ（実行成功・再現性・全37商品ユニーク・形式妥当性） | PASS | `harness/evidence/FEAT-PCODE/G-1/` |
| G-2 | バッチ無回帰（pytest全件緑・recommenderのリフト順が崩れない） | PASS（169 passed, 0 failed） | `harness/evidence/FEAT-PCODE/G-2/` |
| G-3 | テスト実質性（ハリボテでないことの読解確認） | PASS | 本レポート下部「G-3 詳細」 |
| G-4 | 解決APIの独立確認（ハイフン有無・404・products詳細への含有） | PASS | `harness/evidence/FEAT-PCODE/G-4/` |
| G-5 | フロント build + vitest | PASS（build成功／52 tests passed, 0 failed） | `harness/evidence/FEAT-PCODE/G-5/` |
| G-6 | 実ブラウザE2E（手入力→S2遷移／エラー表示／QR直リンクとの等価性） | PASS | `harness/evidence/FEAT-PCODE/G-6/` |

## 受け入れ条件（18章 → HARNESS.md §3）との対応

本機能はAC-1（QR起点フォールバック経路の拡張）に該当する。既存のAC-1〜AC-6自体は本タスクの対象外（新機能固有の検証であり、DoDの再定義は行っていない）。手入力後は既存のQR解決フロー（session作成→`qr_scan`イベント送信→S2遷移）に完全合流することをG-6で確認しており、AC-1の「カメラ不可時のフォールバックで同一画面に到達」という要求と整合する。

---

## G-1: 採番バッチ 詳細

### 実行コマンド
```
cd backend
.venv\Scripts\python.exe -m batch.product_codes   # 1回目
.venv\Scripts\python.exe -m batch.product_codes   # 2回目（再現性確認）
```

### 結果
- 2回とも正常終了（`products.json に商品番号（product_code）を付与しました: 37 件（うちQRマスタ(qr_codes.json)に product_code を併記: 37 件）`。ログはcp932端末表示で文字化けするが内容は正常。証跡: `run1.log` / `run2.log`）。
- **再現性**: 1回目実行後の `products.json`／`qr_codes.json` と2回目実行後のそれらを `diff` した結果、**完全にバイト一致**（差分ゼロ）。さらに、QA着手前の（実装エージェントが生成した）`products.json`／`qr_codes.json` とも完全一致することを確認（`products.before.json` = `products.run1.json` = `products.run2.json`）。証跡: 上記diffコマンドの実行結果（本ツール実行ログに記録済み）。
- **独立検算（QA自作の別実装での再計算）**: QAが `batch/product_codes.py` を読まずに独立に大分類/中分類/小分類の名称ソート採番・個別番号のproduct_id昇順採番ロジックを再実装し、実データ全37件で突合。**全件一致**（`mismatches` 空）。証跡: `harness/evidence/FEAT-PCODE/G-1/verify.log`。
- **全37商品ユニーク**: `len(set(codes)) == 37 == len(products)` を確認（重複0）。証跡: 同上。
- **形式妥当性**: 正規表現 `^\d{2}-\d{2}-\d{2}-\d{3}$` に全37件が一致。不正形式は0件。
- **QRマスタとの整合**: `qr_codes.json` の `type=="product"` エントリ37件すべてに、対応する商品と同一の `product_code` が併記されている（不一致0件）。`type!="product"`（入口QR等）のエントリには `product_code` が付与されていない（0件）ことも確認。

**判定: PASS**

---

## G-2: バッチ無回帰 詳細

### 実行コマンド
```
cd backend
.venv\Scripts\python.exe -m pytest tests -v
```

### 結果
- **169 passed, 0 failed**（1 warning はhttpx非推奨警告のみで無関係）。証跡: `harness/evidence/FEAT-PCODE/G-2/pytest_full.log`。
- うち商品番号関連テストは17件（`test_product_codes.py` 12件 + `test_product_code_resolve.py` 5件）。既存分は152件で、実装指示の「既存152＋新規」と一致。
- **recommenderの独立確認**: バッチ実行済み（`product_code` 付与後）の実データに対し、QAが `HybridRecommender.from_data_dir()` を直接呼び出し、P001の関連商品推薦結果がリフト降順（2.8, 2.8 で非減少確認）であることを確認。`product_code` 付与がrecommenderロジックに影響を与えていないことを実証。証跡: `harness/evidence/FEAT-PCODE/G-2/recommender_independent_check.log`。

**判定: PASS**

---

## G-3: テスト実質性（ハリボテでないことの確認）

### `backend/tests/unit/test_product_codes.py`（12テスト）
読解の結果、以下が実際にアサートされていることを確認した（プレースホルダ／常にtrueになるアサーション等は無い）。
- コード形式（正規表現 `^\d{2}-\d{2}-\d{2}-\d{3}$` を全件チェック）
- 階層採番の安定性（「あ分類」「か分類」の名称ソート順、"01-"/"02-" プレフィックスを具体的に検証。「中1」配下の「小1」「小2」がMM/SSでどう並ぶかまで具体値で検証）
- 個別番号（NNN）が同一小分類内で `product_id` 昇順に001,002,003と振られること（意図的に入力順をシャッフルして検算）
- 全商品ユニーク（同名の中分類・小分類が異なる大分類に存在する意地悪ケースを用意し、上位桁で衝突しないことを確認）
- 決定的・再現性（入力順を変えても結果不変／同一入力を2回実行してJSON文字列まで一致することを確認）
- 入力の並び順・既存フィールドが変更されないこと
- `normalize_product_code` のハイフン有無同一性（空白混入ケースも含む）
- QRマスタへの併記が `type=="product"` のみに限定されること（入口QRは変更されないことを明示的にアサート）
- **実データでの検証**（`tmp_path` に実データをコピーして隔離実行、本番 `data/` を書き換えないよう配慮しつつユニーク性・形式・QRマスタ整合を確認。加えて実データでの再現性（2回実行のバイト一致）も別テストで確認）
- 異常系（`cat_large` 等の必須フィールド欠落時に `KeyError` を送出することを確認。サイレント無視されないことの検証）

いずれも具体的な期待値（プレフィックスの数字、桁位置ごとのassert、コレクション同士の集合比較）を伴っており、ハリボテではない。

### `backend/tests/integration/test_product_code_resolve.py`（5テスト）
- ハイフン付きコードでの解決が `product_id`/`qr_id`/`position`/`product_code` を正しい形状で返すこと（P001の期待値はハードコードでなく実データから動的取得しており、将来の採番変更でテストが無意味に壊れない設計になっている点も良い）
- 数字のみ入力でも同一商品に解決され、ハイフン付きレスポンスと**完全一致**すること
- 未知コードの404＋`code=="PRODUCT_CODE_NOT_FOUND"`＋非空メッセージ
- 数字を含まない不正入力でも例外を起こさず404で返ること（500にならないことの明示的な回帰確認）
- `GET /api/products/{id}` のレスポンスに `product_code` が含まれること

これらもモックへの丸投げではなく実データ・実APIクライアント（`client`フィクスチャ経由のFastAPI TestClient想定）に対する検証であり、QA自身がG-4で同一エンドポイントを別途独立にcurlで叩いた結果とも整合した（下記G-4参照）。ハリボテではない。

### `frontend/src/pages/__tests__/ScanPage.test.tsx`（新規3テスト、`describe("ScanPage (S1) - 商品番号（手入力）による直接遷移")` 配下）
- 商品番号入力→送信→`GET /api/product-code/...`→`POST /api/session`（`qr_id`が正しく渡ること）→`qr_scan`イベント送信→S2（`product-page`）遷移、という一連の呼び出し順序とペイロードを `calls` 配列から具体的に検証
- ハイフン無し数字列でも同様に解決されること
- 無効な商品番号で `product-code-error`（`エラーメッセージに「見つかりません」を含む`ことまで検証）が表示され、かつ `product-page` へは遷移しない（`queryByTestId` が `null` であることを明示的に確認）こと

モックはAPI呼び出しの入出力契約に対するものであり、UIロジック自体（フォーム送信ハンドラ、状態遷移、エラー表示分岐）は実コンポーネントを実際にレンダリングして検証しているため、ハリボテではない。

**判定: PASS**

---

## G-4: 解決APIの独立確認 詳細

### 実行コマンド（backend起動後、QAが直接curlで実行）
```
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
curl http://localhost:8000/api/product-code/03-02-01-001      # P001, ハイフン有り
curl http://localhost:8000/api/product-code/030201001         # P001, ハイフン無し
curl http://localhost:8000/api/product-code/03-01-02-001      # P010, ハイフン有り
curl http://localhost:8000/api/product-code/030102001         # P010, ハイフン無し
curl http://localhost:8000/api/products/P010
curl http://localhost:8000/api/product-code/99-99-99-999      # 未知コード
curl http://localhost:8000/api/product-code/not-a-code        # 不正入力
```

### 結果（実在コード例と解決結果）
| 入力 | 商品 | HTTPステータス | レスポンス |
|---|---|---|---|
| `03-02-01-001` | P001 | 200 | `{"product_id":"P001","qr_id":"QR-PRODUCT-P001","position":{"floor":1,"x":17,"y":18},"product_code":"03-02-01-001"}` |
| `030201001` | P001 | 200 | 上と**完全一致** |
| `03-01-02-001` | P010 | 200 | `{"product_id":"P010","qr_id":"QR-PRODUCT-P010","position":{"floor":1,"x":97,"y":90},"product_code":"03-01-02-001"}` |
| `030102001` | P010 | 200 | 上と**完全一致** |
| （未知）`99-99-99-999` | - | 404 | `{"code":"PRODUCT_CODE_NOT_FOUND","message":"商品番号 99-99-99-999 に該当する商品が見つかりません。番号をご確認ください。"}` |
| （不正形式）`not-a-code` | - | 404 | `{"code":"PRODUCT_CODE_NOT_FOUND",...}`（500にならず明確な404） |

`GET /api/products/P010` のレスポンスにも `"product_code":"03-01-02-001"` が含まれることを確認。

証跡: `harness/evidence/FEAT-PCODE/G-4/resolve_p001.log`, `resolve_p010_and_errors.log`, `uvicorn.log`。

**判定: PASS**

---

## G-5: フロント build + test 詳細

### 実行コマンド
```
cd frontend
npm run build
npm run test -- --run
```

### 結果
- `npm run build`: **成功**（`tsc -b && vite build` エラー無し。証跡: `harness/evidence/FEAT-PCODE/G-5/build.log`）
- `npm run test`: **Test Files 8 passed (8) / Tests 52 passed (52)**、失敗0。既存49件＋新規3件（`ScanPage.test.tsx` の商品番号関連describeブロック）と一致。証跡: `harness/evidence/FEAT-PCODE/G-5/vitest.log`

**判定: PASS**

---

## G-6: 実ブラウザ E2E 詳細

backend（`uvicorn`, port 8000）／frontend（`npm run dev`, port 5173, `.claude/launch.json` の `frontend-dev` 構成）を起動し、Claude_Browser MCPで操作。スクリーンショットは本環境では取得せず、`read_page`（アクセシビリティツリー）と `get_page_text`（可視テキスト）をDOM/テキスト証跡として使用した（テキスト・DOM構造双方から遷移先・要素の存在・内容を一意に特定できるため、HARNESS.mdの「screenshot不可環境ならテキスト/DOM証跡で可」に該当する扱いとした）。

### シナリオ1: 有効な商品番号→S2遷移
1. `http://localhost:5173/` を開く（S1、`商品番号` 入力欄・`商品へ進む` ボタンが表示されることを確認）
2. `product-code-input`（`read_page` で `textbox "例: 01-03-02-001"` として検出）に `03-01-02-001`（P010の実コード、G-4で解決確認済み）を入力
3. `product-code-submit`（`button "商品へ進む" type="submit"`）をクリック
4. **S2（商品詳細）へ遷移**し、`get_page_text` で「ネイビークッション」「商品番号: 03-01-02-001（QR下部に記載）」が表示されることを確認（`product-code` testid相当の要素、`read_page` で該当generic要素として検出）
5. 同一商品のQR直リンク `/s/QR-PRODUCT-P010` に別途アクセスし、**完全に同一のページ内容**（商品名・価格・商品番号・関連商品・コーディネート）に到達することを確認 → 手入力とQR/URL直リンクの**等価性**を確認

証跡: `harness/evidence/FEAT-PCODE/G-6/e2e-01-valid-code-P010.txt`

### シナリオ2: 無効な商品番号→エラー表示
1. `http://localhost:5173/scan` を開く
2. `product-code-input` に `99-99-99-999`（G-4で404確認済みの未知コード）を入力し送信
3. `read_page` で `alert` roleの要素（`product-code-error` testid相当）に「商品番号 99-99-99-999 に該当する商品が見つかりません。番号をご確認ください。」が表示されることを確認
4. ページはS1に留まり、商品詳細ページへは遷移しないことを確認

証跡: `harness/evidence/FEAT-PCODE/G-6/e2e-02-invalid-code-error.txt`

**判定: PASS**

---

## 実行したコマンド（再現用・要約）

```bash
# G-1
cd backend
.venv\Scripts\python.exe -m batch.product_codes   # x2（再現性確認）
# 独立検算スクリプト実行（harness/evidence/FEAT-PCODE/G-1/verify.log 参照）

# G-2
cd backend
.venv\Scripts\python.exe -m pytest tests -v
# recommender独立確認スクリプト実行

# G-4（別ターミナルでbackend起動）
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
curl http://localhost:8000/api/product-code/03-02-01-001
curl http://localhost:8000/api/product-code/030201001
curl http://localhost:8000/api/product-code/03-01-02-001
curl http://localhost:8000/api/product-code/030102001
curl http://localhost:8000/api/products/P010
curl http://localhost:8000/api/product-code/99-99-99-999
curl http://localhost:8000/api/product-code/not-a-code

# G-5
cd frontend
npm run build
npm run test -- --run

# G-6（backend + frontend dev起動後、Claude_Browser MCPで操作）
npm --prefix frontend run dev   # port 5173
# navigate http://localhost:5173/ -> 商品番号入力 03-01-02-001 -> 送信 -> S2遷移確認
# navigate http://localhost:5173/s/QR-PRODUCT-P010 -> 同一ページに到達（等価性確認）
# navigate http://localhost:5173/scan -> 商品番号入力 99-99-99-999 -> 送信 -> エラー表示確認
```

## FAIL 詳細
なし（全ゲート PASS）。

## 前進判定
- [x] 当該ゲートの全項目 PASS かつ テスト緑 → 次段階へ
- [ ] RED → 実装エージェントへ差し戻し（試行回数: 0/3）
- [ ] 3回超過 → 人間へエスカレーション

## 補足（実装への所見・改善提案。FAILではない）
- なし。実装は仕様（曖昧部分の解釈根拠を含む）・テスト・証跡整合の点で問題を検出しなかった。
