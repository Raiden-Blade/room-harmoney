"""Room Harmony backend - FastAPI アプリのエントリポイント。

17章 API仕様の8エンドポイントを `app/routers/` に分割して結線する（G2 API結合）。
推薦（B1 HybridRecommender）・経路（B2 RouteGraphBuilder）・データ層（dataio/ 経由の
リポジトリ）は `app/dependencies.py` の `Depends` を通じて注入し、差し替え可能にする。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .errors import register_exception_handlers
from .routers import (
    admin,
    coordinates,
    events,
    products,
    qr,
    recommendations,
    route,
    session,
    store_map,
)

app = FastAPI(
    title="Room Harmony API",
    description="来店客向けアプリ Room Harmony のバックエンドAPI（17章 API仕様）",
    version="0.2.0",
)

# フロント開発用に localhost からの CORS を許可する。
# 許可オリジンは `CORS_ALLOW_ORIGINS`（カンマ区切り）環境変数から読み込む
# （QA G3 G-G3-7 申し送り対応: 従来はハードコードで `vite preview`(4173) 等の
# 検証ができなかった）。未設定時の既定値は `app/config.py` の
# `DEFAULT_CORS_ALLOW_ORIGINS` を参照（Vite dev の5173とpreviewの4173を
# localhost/127.0.0.1 両方で許可）。本番オリジンは同環境変数で絞り込む
# （未確定事項: 前提を採用しコメントで明記）。
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_settings.cors_allow_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(session.router)
app.include_router(qr.router)
app.include_router(products.router)
app.include_router(recommendations.router)
app.include_router(coordinates.router)
app.include_router(route.router)
app.include_router(store_map.router)
app.include_router(events.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict:
    """ヘルスチェック。デプロイ/起動確認用の最小エンドポイント。"""
    return {"status": "ok"}
