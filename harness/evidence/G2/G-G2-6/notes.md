# G-G2-6 エラーコード（19章）検証

| ケース | エンドポイント | 期待 | 実際 | 根拠 |
|---|---|---|---|---|
| 不正qr_id（POST /api/session） | `POST /api/session` | 404 + code | 404 `QR_NOT_FOUND` | test_session.py::test_create_session_with_unknown_qr_returns_404 |
| 不正qr_id（GET /api/qr） | `GET /api/qr/{qr_id}` | 404 + code | 404 `QR_NOT_FOUND` | test_qr.py::test_resolve_unknown_qr_returns_404 |
| 不正from_qr（route） | `GET /api/route` | 404 + code | 404 `QR_NOT_FOUND` | test_route.py::test_route_unknown_from_qr_returns_404 |
| 存在しないproduct_id（products） | `GET /api/products/{id}` | 404 + code | 404 `PRODUCT_NOT_FOUND` | test_products.py::test_get_unknown_product_returns_404 |
| 存在しないproduct_id（recommendations） | `GET /api/recommendations` | 404 + code | 404 `PRODUCT_NOT_FOUND` | test_recommendations.py::test_recommendations_unknown_product_with_valid_session_returns_404 |
| 存在しないto_product（route） | `GET /api/route` | 404 + code | 404 `PRODUCT_NOT_FOUND` | test_route.py::test_route_unknown_to_product_returns_404 |
| 存在しないcoordinate_id | `GET /api/coordinates/{id}` | 404 + code | 404 `COORDINATE_NOT_FOUND` | test_coordinates.py::test_get_unknown_coordinate_returns_404 |
| 範囲外floor | `GET /api/store-map/{floor}` | 404 + code | 404 `FLOOR_NOT_FOUND` | test_store_map.py::test_get_out_of_range_floor_returns_404 |
| 経路なし（全目的地到達不能） | `GET /api/route` | 404 + code | 404 `ROUTE_NOT_FOUND` | 実データは全ノード連結（G1で連結性を確認済み）のためテストスイート内では再現不可。QAが `route_builder` を dependency_overrides で「常に到達不能」を返すスタブに差し替えて自作リクエストで独立検証（実装コードは変更していない）。`evidence/G2/G-G2-6/adhoc_route_not_found.txt` に実行ログ。結果: `404` + `{"code": "ROUTE_NOT_FOUND", ...}` を確認。 |
| 許可外event_type | `POST /api/events` | 422 + code | 422 `INVALID_EVENT_TYPE` | test_events.py::test_post_event_with_disallowed_event_type_returns_422 |
| 未知session_id（events） | `POST /api/events` | 404 + code | 404 `SESSION_NOT_FOUND` | test_events.py::test_post_event_with_unknown_session_id_returns_404 |
| 必須フィールド欠如 | `POST /api/events` | 422 | 422（Pydantic標準） | test_events.py::test_post_event_missing_required_field_returns_422 |
| 来店ロック（セッション無し/偽ID） | recommendations/route | 409 + code | 409 `VISIT_LOCK_REQUIRED` | G-G2-4参照 |

すべてのエラーレスポンスが `{"code": ..., "message": ...}` という統一フォーマット
（`app/errors.py` の `ApiError`/`register_exception_handlers`）で返ることをコード上
確認済み（FastAPI標準の `{"detail": ...}` 形式ではなく、トップレベルに`code`/`message`）。

**判定: PASS**
