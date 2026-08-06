# G-G2-5 experiment_group（AC-4）付与検証

## POST /api/session でのレスポンス付与
`test_session.py::test_create_session_with_valid_qr_returns_expected_shape`
→ レスポンスキー集合が `{"session_id","start","floor","experiment_group"}` と厳密一致、
`experiment_group` が `{TREATMENT, CONTROL}` のいずれかであることを確認。

## 各イベントへの付与（DBから直接検証）
- `session_start`: `test_session.py::test_create_session_records_session_start_event`
  → `store.list_events()` で読み出したイベントの `event["experiment_group"]` が
  レスポンスの `experiment_group` と一致することをDB側から確認。payload内にも
  `experiment_group` が含まれる。
- `related_view`: `test_recommendations.py::test_recommendations_records_related_view_event_with_experiment_group`
  → DB上のイベントの `experiment_group` がセッションのものと一致。
- `route_view`: `test_route.py::test_route_records_route_view_event_with_experiment_group`
  → 同上。
- `coordinate_view`: `test_coordinates.py::test_get_coordinate_with_session_id_records_coordinate_view_event`
  → 同上。
- `POST /api/events`（任意イベント）: `test_events.py::test_post_allowed_event_type_is_recorded_with_experiment_group`
  および `test_post_event_without_client_supplied_experiment_group_still_gets_one`
  → クライアントが `experiment_group` をpayloadに含めなくても、サーバがsession_idから
  引いた値を必ず付与することを確認（クライアント偽装耐性）。

## ライブHTTPでの独立再現
uvicorn実サーバで `session_start`(event_id=1) → `related_view`(event_id=2、
GET /api/recommendations呼出し時に自動記録) → `chatbot_open`(event_id=3、
POST /api/events) と3件連続で記録され、いずれも `experiment_group="control"`
（該当セッションの割付値）で一致することを確認した
（evidence/G2/G-G2-9/live_http_flow_notes.txt）。

## 割付ロジックの検証
`test_experiment_group.py` にて、比率0/1での決定的な全件確認、シード固定時の
再現性、DI経由の差し替え可能性を検証。

**判定: PASS**
