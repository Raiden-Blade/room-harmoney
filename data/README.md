# data/ サンプルデータ仕様

要件定義書 11章（サンプルデータ仕様）・6章（データモデル）、`docs/DESIGN.md` 2章（確定版データモデル）、
`docs/DECISIONS.md`（#2 中分類併売率／#4 4フロア目黒通り店／#5 会員は集計3指標のみ）に準拠。
実データに差し替え可能な構造（JSON。将来 `backend/ingest/` のアダプタで実データへ置換）。

生成スクリプト：`scratchpad/gen_data.py` 相当のロジックで、内部整合性（参照整合・グラフ連結性）を
アサートしたうえで書き出したもの。仕様や商品を追加する場合も、同様の整合チェックを通してから
再生成すること。

---

## products.json（商品マスタ）

30〜50点。目黒通り店（4フロア）を想定し、複数の大/中/小分類・複数色をまたぐ。

| 列 | 型 | 説明 |
|---|---|---|
| product_id | string | 商品ID（`P001`...） |
| name | string | 商品名 |
| cat_large | string | 大分類（フロア対応: リビング/ベッドルーム/ダイニング・キッチン/収納・ワークスペース） |
| cat_mid | string | 中分類（`co_purchase.json` の `cat_mid_a/b` と対応） |
| cat_small | string | 小分類 |
| color | string | 色 |
| price | int | 価格（円） |
| image_url | string | 画像URL（ダミー） |
| floor | int | フロア（1〜4） |
| zone | string | ゾーン記号（A/B/C/D=通常ゾーン、SUB=サブ通路） |
| x, y | float | 売場座標（フロア内 0〜100 のローカル座標） |
| sub_passage_flag | bool | サブ通路商品か（`zone == "SUB"` の商品で true。関連商品の経路優先案内に利用） |

37点、うち6点が `sub_passage_flag: true`。

## co_purchase.json（併売/リフトテーブル・中分類ペア単位）／co_purchase_source.json（上流入力）

**フェーズ2-A：`co_purchase.json` は手書きではなく、`backend/batch/lift_batch.py`
（リフト算出バッチ）による生成物**。DECISIONS.md #2 により、実データはトランザクション生データが
無く中分類レベルの集計併売率が基本となる前提。そのため、上流の「素の集計」を
`co_purchase_source.json`（中分類ごとの単体支持度 `support` と、中分類ペアごとの共起支持度
`co_support`）として保持し、以下の明示式で `co_purchase.json` を再現可能に算出する。

```
support(A,B)      = co_support                         … P(A∩B) そのもの
confidence(A,B)   = co_support / support(A)             … P(B|A)（方向は cat_mid_a → cat_mid_b）
lift(A,B)         = co_support / (support(A) * support(B))
co_purchase_rate  = co_support                          … 併売率の基本値（support と同値）
high_lift_low_corate = (lift >= LIFT_THRESHOLD=2.0) and (co_purchase_rate <= CORATE_THRESHOLD=0.045)
```

再生成コマンド（cwd=`backend`）:

```powershell
.venv\Scripts\python.exe -m batch.lift_batch
```

実データ差し替え時は、`co_purchase_source.json` の `support`（中分類の周辺確率）・`co_support`
（ペアの共起確率）をトランザクション生データからの実測値に置き換え、上記コマンドを再実行すれば
`co_purchase.json` が更新される（`RecommenderInterface` 実装は co_purchase テーブルの形
（cat_mid_a/b, lift, high_lift_low_corate）にのみ依存するため、算出方法を差し替えても実装への
影響はない）。単体テストは `backend/tests/unit/test_lift_batch.py`（手計算・境界値・再現性・
参照整合を検証）。

| 列 | 型 | 説明 |
|---|---|---|
| cat_mid_a / cat_mid_b | string | 中分類ペア（products.json の cat_mid を参照） |
| co_purchase_rate | float | 併売率（基本値。support と同値として扱う近似） |
| support | float | 支持度（近似） |
| confidence | float | 信頼度（近似） |
| lift | float | リフト（近似） |
| high_lift_low_corate | bool | 「リフト高×併売率低」＝伸びしろフラグ（`lift>=2.0` かつ `support<=0.045` で判定） |

16ペア中6ペアが `high_lift_low_corate: true`（意図的に配置した「伸びしろ」ペア。フロアを跨ぐ
組み合わせが多く、コーディネート・ルート提案でのクロスセル訴求を想定）。

## coordinates.json（コーディネートマスタ）

テーマ違いで5セット（3〜6商品構成）。`product_ids` は `products.json` の実在IDのみを参照。

| 列 | 型 | 説明 |
|---|---|---|
| coordinate_id | string | コーデID |
| name | string | 名称 |
| theme | string | テーマ（ナチュラル/モダン/北欧/シンプル/アーバン） |
| product_ids | string[] | 構成商品ID |
| image_url | string | 完成イメージ（ダミー） |
| total_price_estimate | int | 合計金額目安（構成商品の price 合計。生成時に自動計算） |

## store_map.json（店舗マップ・4フロア）

フロアごとに `floorplan`（ゾーン矩形の簡易JSON）、`zones`、`waypoints`（グラフノード）、
`edges`（通路の接続・距離）、`sub_passages` を持つ。加えてトップレベルの `inter_floor_edges` で
階段・エレベーターの前後フロア接続を表現する（1F-2F, 2F-3F, 3F-4F）。

- `waypoints[].type`：`通路` / `階段` / `EV` / `入口`（1Fのみ）/ `ゾーン` / `サブ通路` / `商品近傍`
- `edges[].distance`：ノード間のユークリッド距離（通路内）または固定コスト（階段15.0 / EV12.0）
- 全ノードが1つの連結成分になるよう生成時にUnion-Findで検証済み（`backend/tests/unit` でも
  実データを読み込んで再検証する）。
- サブ通路（`サブ通路` ノード）はゾーンより通路ハブ（c5）までの経路が単線かつ迂回気味になる
  よう配置し、「通過率が低い」という前提を経路コスト面でも表現している。

## qr_codes.json（QRマスタ）

入口QR1件＋商品QR（全商品分＝37件）で計38件。

| 列 | 型 | 説明 |
|---|---|---|
| qr_id | string | `QR-ENTRANCE-001` または `QR-PRODUCT-{product_id}` |
| type | string | `entrance` / `product` |
| product_id | string\|null | 商品QRの場合のみ設定 |
| floor / x / y | 数値 | 設置座標 |
| direct_url | string | カメラ不可時のURL直リンク（ダミードメイン） |

## aggregates.json（集計3指標・オプショナル）

DECISIONS.md #5：会員個票・購入履歴は扱わず、`customer_total`（客総数）・`store_count`（店舗数）・
`member_count`（会員数）の集計3指標のみをサンプル値として保持する。

**欠損時フォールバック**：ファイルが存在しない、または空/壊れたJSONの場合でも、集計3指標を
参照する側は `None`（未取得）を返して処理を継続できる設計とする（後続のAPI実装で
`backend/app` 側にローダを実装する際、本ファイル欠損を例外にしないこと）。G1時点では
`recommender`/`routing` はこのファイルに依存しないため、G1のテストには影響しない。

## events.empty.json

イベントログ（`session_id, timestamp, event_type, payload, experiment_group`）は空配列 `[]` で
開始する。書き込み・スキーマ実装はG2（API）段階で行う。

## pos_metrics.json（POS突合スロット・オプショナル／フェーズ2-B1）

`GET /api/admin/kpi`（10章 計測・ログ設計／12章 KPI）のPOS突合スロットで参照する、
experiment_group（`treatment`/`control`）別の集計値のサンプル。ファイルが無くても
`backend/app/dependencies.py` の `get_pos_metrics` が `None` にフォールバックし、
KPI集計API自体は500にならず `pos_metrics: null`（N/A）を返す。

| キー | 型 | 説明 |
|---|---|---|
| treatment.co_purchase_rate / control.co_purchase_rate | float | 併売率（12章） |
| treatment.items_per_purchase / control.items_per_purchase | float | 買上点数（12章） |
| treatment.spend_per_customer / control.spend_per_customer | int | 客単価（12章・円） |

実データ差し替え時は、POSレジ集計をA/B群（`sessions` テーブルの `experiment_group`）で
突合したうえで同じキー構成のJSONに置き換える。

---

## 実データ差し替え手順（イメージ）

1. ニトリECの商品JSON（手動取得分）を `backend/ingest/` の変換アダプタに入力する。
2. アダプタが `product_id, name, cat_large/mid/small, color, price, image_url` を
   `products.json` の列に変換する（`floor/zone/x/y/sub_passage_flag` は別途、店舗の実測データ
   または什器配置台帳から補完する）。
3. 併売率の実データ（中分類集計、または将来トランザクション生データ）が入手でき次第、
   `co_purchase.json` の `support/confidence/lift` を実測値で再計算する
   （近似式は本READMEの `co_purchase.json` 節を参照）。
4. コーディネートマスタはスタイリング担当の入稿データ（構成商品ID・テーマ・完成イメージ）を
   そのまま `coordinates.json` の形に変換する。
5. 店舗マップは実測フロアプラン・什器配置から `waypoints/edges` を作成し、Union-Find等で
   全ノード連結性を確認してから投入する。
6. QRマスタは発行済み `qr_id` 体系があればそれを、無ければ本サンプルの命名規則
   （`QR-ENTRANCE-...` / `QR-PRODUCT-{product_id}`）を踏襲して発行する。
