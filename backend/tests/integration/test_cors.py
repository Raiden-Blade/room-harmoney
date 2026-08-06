"""CORS許可オリジンの結合テスト（QA G3 G-G3-7 申し送り対応の回帰）。

`backend/app/main.py` はアプリ起動時に `app/config.py` の `Settings.cors_allow_origins`
（既定は `CORS_ALLOW_ORIGINS` 環境変数、未設定時はVite dev/previewの既定値）を読み込んで
`CORSMiddleware` に渡す。QA証跡（`gate-G3-20260805.md` G-G3-7）では、CORS許可が
`http://localhost:5173` にハードコードされていたため `vite preview`（本番ビルド配信、
既定4173）からのAPI呼び出しがブロックされ、StrictModeのeffect二重実行が本番ビルドでも
再現するかどうかを検証できなかった。本テストは実際に起動した `app`（環境変数未設定＝
既定値）に対して `Origin` ヘッダ付きリクエストを送り、`vite preview` のオリジンが
実際に許可されることを確認する。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_vite_preview_origin_4173_is_allowed_by_default() -> None:
    """既定設定（CORS_ALLOW_ORIGINS未設定）で `vite preview`（4173）からの呼び出しを許可する。"""
    response = client.get("/health", headers={"Origin": "http://localhost:4173"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:4173"


def test_vite_dev_origin_5173_is_allowed_by_default() -> None:
    """既定設定で従来通り Vite dev サーバ（5173）からの呼び出しも許可する（後方互換）。"""
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_unlisted_origin_is_not_granted_cors_access() -> None:
    """許可リストに無いオリジンには `access-control-allow-origin` を付与しない
    （全許可への後退がないことの回帰確認）。"""
    response = client.get("/health", headers={"Origin": "https://evil.example.com"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
