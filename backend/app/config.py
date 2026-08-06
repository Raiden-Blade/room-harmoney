"""アプリ設定（.env.example / 16章 リポジトリ構成 準拠）。

前提（コメントとして残す・未確定事項寄りの実装判断）:
本アプリは `uvicorn app.main:app` で起動する素の FastAPI であり、`.env` ファイルの
自動読み込みは行わない（python-dotenv 等を必須依存にしない）。環境変数は起動シェル側
（あるいはデプロイ環境のプロセスマネージャ）で `.env` の内容を export しておく前提とし、
未設定の場合は `.env.example` に記載のデフォルト値にフォールバックする。
これにより開発中の `pytest` 実行（環境変数未設定）でも常に決定的な既定動作になる。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# backend/app/config.py から見て ../../ が room-harmony リポジトリのルート
# （backend/dataio/loader.py の DEFAULT_DATA_DIR と同じ規約に合わせる）。
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_DATABASE_URL = "sqlite:///./data/room_harmony.db"
DEFAULT_STORE_ID = "meguro-dori"
DEFAULT_EXPERIMENT_GROUP_MODE = "random"
DEFAULT_EXPERIMENT_GROUP_RATIO = 0.5
DEFAULT_CHATBOT_BASE_URL = "https://example.invalid/chatbot"
DEFAULT_FRONTEND_ORIGIN = "http://localhost:5173"

# CORS許可オリジンの既定値（QA G3 G-G3-7 申し送り対応）。
# 開発時の Vite dev サーバ（5173）に加え、`vite preview`（本番ビルド配信、既定4173）も
# 検証できるよう既定に含める。127.0.0.1 版も含めるのは、ブラウザによって
# localhost と 127.0.0.1 を別オリジン扱いするため（`docs/HARNESS.md` の検証手順が
# どちらの表記でアクセスしても動くようにする前提）。本番オリジンは
# `CORS_ALLOW_ORIGINS`（カンマ区切り）環境変数で上書きする。
DEFAULT_CORS_ALLOW_ORIGINS = (
    "http://localhost:5173,"
    "http://127.0.0.1:5173,"
    "http://localhost:4173,"
    "http://127.0.0.1:4173"
)


def _parse_origins(raw: str) -> tuple[str, ...]:
    """カンマ区切りのオリジン文字列をパースする（前後空白除去・空要素除外）。"""
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


@dataclass(frozen=True)
class Settings:
    """`.env.example` に対応する設定値。既定値は同ファイルの値に合わせる。"""

    database_url: str = DEFAULT_DATABASE_URL
    store_id: str = DEFAULT_STORE_ID
    experiment_group_mode: str = DEFAULT_EXPERIMENT_GROUP_MODE
    experiment_group_ratio: float = DEFAULT_EXPERIMENT_GROUP_RATIO
    chatbot_base_url: str = DEFAULT_CHATBOT_BASE_URL
    frontend_origin: str = DEFAULT_FRONTEND_ORIGIN
    cors_allow_origins: tuple[str, ...] = _parse_origins(DEFAULT_CORS_ALLOW_ORIGINS)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            store_id=os.environ.get("STORE_ID", DEFAULT_STORE_ID),
            experiment_group_mode=os.environ.get(
                "EXPERIMENT_GROUP_MODE", DEFAULT_EXPERIMENT_GROUP_MODE
            ),
            experiment_group_ratio=float(
                os.environ.get("EXPERIMENT_GROUP_RATIO", DEFAULT_EXPERIMENT_GROUP_RATIO)
            ),
            chatbot_base_url=os.environ.get("CHATBOT_BASE_URL", DEFAULT_CHATBOT_BASE_URL),
            frontend_origin=os.environ.get("FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN),
            cors_allow_origins=_parse_origins(
                os.environ.get("CORS_ALLOW_ORIGINS", DEFAULT_CORS_ALLOW_ORIGINS)
            ),
        )

    @property
    def database_path(self) -> Path:
        """`DATABASE_URL`（sqlite:///path 形式）からファイルパスを取り出す。

        相対パスは `dataio.DEFAULT_DATA_DIR` と同じ規約でリポジトリルート基準に解決する
        （`backend` から起動しても `data/` を正しく指すようにするため）。
        """
        raw = self.database_url
        prefix = "sqlite:///"
        rel = raw[len(prefix):] if raw.startswith(prefix) else raw
        path = Path(rel)
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
