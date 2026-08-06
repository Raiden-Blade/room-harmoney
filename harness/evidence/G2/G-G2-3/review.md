# G-G2-3 テスト実質性レビュー（ハリボテ検出）

`backend/tests/integration` 配下 10ファイル・41件を全件読解した。

## レビュー観点
- 各テストが実際の HTTP レスポンス（status_code・body の形状・具体的な値）をアサートしているか
- 異常系（存在しないID・セッション無し・不正な event_type・範囲外floor）が、期待するHTTPコードと`code`フィールドまで厳密に検証されているか
- イベントログ（10章）の記録内容・`experiment_group`の伝播を、DBから直接読み出して検証しているか（レスポンスの自己申告だけで終わっていないか）
- `assert response.status_code == 200` だけで終わる「空アサート」のテストが無いか

## ファイル別所見

| ファイル | 件数 | 所見 |
|---|---|---|
| test_health.py | 1 | ステータス+ボディ完全一致を確認。スモークとして妥当。 |
| test_session.py | 5 | レスポンスキー集合の厳密一致(`set(body.keys())`)、座標値、`QR_NOT_FOUND`コード、`store.list_events`でDB直読みしてpayload内容(`qr_id`,`qr_type`,`floor`,`store_id`,`experiment_group`)を検証、`store.get_session`でDB行の永続化も確認。ハリボテなし。 |
| test_qr.py | 3 | レスポンス全体を`==`で厳密比較（type/product_id/position/direct_url）。入口QRは`product_id is None`まで確認。404時`code`確認。ハリボテなし。 |
| test_products.py | 2 | 商品詳細の全フィールド値を直接比較（`cat_large`,`cat_mid`,`color`,`price`,`floor`,`zone`）。ハリボテなし。 |
| test_recommendations.py | 7 | AC-5来店ロック(409+`VISIT_LOCK_REQUIRED`)をセッション無し/偽セッションIDの両方で確認。リフト降順を`cat_mid`の並びと`lift`列の両方で厳密検証（`sorted(reverse=True)`との一致だけでなく先頭3件/中3件/末尾2件の具体値まで固定値比較）。`high_lift_low_corate`フラグの厳密検証。起点商品を含むコーディネートのみ返ることを集合演算で確認。`related_view`イベントをDBから直接読み出しpayload内容まで確認。ハリボテなし。 |
| test_coordinates.py | 4 | 構成商品の集合一致、合計金額目安の具体値(70690)、404の`code`、`coordinate_view`イベントのDB直接確認。session_id無しでも200（coordinatesは来店ロック対象外という実装方針の明示的検証）。ハリボテなし。 |
| test_route.py | 7 | AC-5来店ロック確認。単一目的地の起点/終点座標を`pytest.approx`で厳密検証、サブ通路経由の有無、複数目的地の巡回順(`visiting_order`)を具体的なproduct_id列で検証、未知QR/未知商品の404+code、`route_view`イベントのDB直接確認（`from_qr`,`visiting_order`）。ハリボテなし。 |
| test_store_map.py | 2 | フロアデータのキー存在・waypoints非空、範囲外floorの404+`FLOOR_NOT_FOUND`。 |
| test_events.py | 5 | `experiment_group`がクライアント指定無しでも必ず付与されることを明示的に検証（AC-4の核心）。許可外`event_type`の422+`INVALID_EVENT_TYPE`、未知セッションの404+`SESSION_NOT_FOUND`、必須フィールド欠如の422。DBに実際に1件だけ記録されていることまで確認。ハリボテなし。 |
| test_experiment_group.py | 5 | 割付比率0/1での決定的な全件確認、シード固定での再現性確認、DI経由の差し替え可能性を実際にoverrideして確認。ハリボテなし。 |

## 結論
41件すべてが「入力データや実装ロジックが壊れれば確実に失敗する」構造になっており、
`assert response.status_code == 200` のみで終わる空アサート（ハリボテ）は皆無だった。
特に AC-4（experiment_group付与）・AC-5（来店ロック）は複数エンドポイント・複数ケース
（セッション無し／偽ID／DIオーバーライド）で多角的に検証されている。

**判定: PASS（ハリボテなし）**
