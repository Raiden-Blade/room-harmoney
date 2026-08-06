"""スモーク結合テスト: GET /health が 200 と {"status": "ok"} を返すことを確認する。

step3 ヘルスチェック（スモーク結合）。HARNESS.md の G2 結合ゲート（`cd backend && py -m pytest tests/integration -v`）で実行される。
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200_and_ok_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
