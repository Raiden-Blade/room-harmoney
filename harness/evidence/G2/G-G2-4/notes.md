# G-G2-4 来店ロック（AC-5）検証

## テストによる確認（backend/tests/integration）
- `test_recommendations.py::test_recommendations_without_session_id_returns_409`
  → session_id無し → 409 + `code=VISIT_LOCK_REQUIRED`
- `test_recommendations.py::test_recommendations_with_bogus_session_id_returns_409`
  → 実在しないsession_id → 409 + `code=VISIT_LOCK_REQUIRED`
- `test_route.py::test_route_without_session_returns_409`
  → session_id無し → 409 + `code=VISIT_LOCK_REQUIRED`
- 有効セッションあり（`active_session`フィクスチャ経由）では、両エンドポイントとも200で成功
  （`test_recommendations_related_are_sorted_by_lift_descending`、`test_route_single_destination_returns_waypoint_list`ほか多数）。

## ライブHTTPでの独立再現（G-G2-9と共通）
uvicorn実サーバ（127.0.0.1:8811）に対し、session_id無しで
`GET /api/recommendations?product_id=P001` を叩いた結果:
```
HTTP:409
{"code":"VISIT_LOCK_REQUIRED","message":"この機能を利用するには、店頭のQRコードを読み取って来店セッションを開始してください。"}
```
（evidence/G2/G-G2-9/live_http_flow_notes.txt 参照）

## 実装確認
`backend/app/dependencies.py` の `require_active_session` が、
`recommendations`/`route` の両ルータで `Depends` として結線されていることを確認
（`app/routers/recommendations.py:24`, `app/routers/route.py:33`）。
`coordinates` エンドポイントは来店ロック対象外（実装方針として明示、
`test_coordinates.py::test_get_coordinate_without_session_id_does_not_error` で確認）。

**判定: PASS**
