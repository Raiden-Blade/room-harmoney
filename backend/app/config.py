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

# 管理系API（17章「管理系は認証必須」）のトークン照合用の既定値。
# 開発用のダミー値であり、本番では必ず `.env` の `ADMIN_API_TOKEN` で上書きすること
# （パスワード入力等は要件外のため、単純な共有トークン照合とする＝前提。コメントで明記）。
DEFAULT_ADMIN_API_TOKEN = "dev-admin-token-change-me"

# 来店判定（フェーズ3-B / DECISIONS.md #7「QRスキャン起動を基本、Wi-Fi/ジオフェンスは
# 拡張余地として設計」）。既定は "qr"（QRのみ＝従来と完全に同一挙動）。
# "qr+geofence" / "qr+wifi" / "qr+geofence+wifi" のように "+" 区切りで追加検証を
# 合成できる（`app/visit.py` の `resolve_verifier` 参照）。
DEFAULT_VISIT_VERIFICATION_MODE = "qr"

# ジオフェンス既定値: 目黒通り店（DECISIONS.md #4 のベース店舗）付近の妥当なダミー座標。
# 実測値ではなく開発用の代表値（東京都目黒区、目黒通り沿いの店舗を想定した座標）。
# 本番導入時は実店舗の測量値に `.env` で置き換えること。
DEFAULT_STORE_GEOFENCE_LAT = 35.6203
DEFAULT_STORE_GEOFENCE_LNG = 139.6883
DEFAULT_STORE_GEOFENCE_RADIUS_M = 150.0

# Wi-Fi既定値: 開発用のダミーSSID（カンマ区切りで複数指定可）。
DEFAULT_STORE_WIFI_SSIDS = "Nitori-Free-Wifi,Nitori-Guest-Wifi"

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
    admin_api_token: str = DEFAULT_ADMIN_API_TOKEN
    visit_verification_mode: str = DEFAULT_VISIT_VERIFICATION_MODE
    store_geofence_lat: float = DEFAULT_STORE_GEOFENCE_LAT
    store_geofence_lng: float = DEFAULT_STORE_GEOFENCE_LNG
    store_geofence_radius_m: float = DEFAULT_STORE_GEOFENCE_RADIUS_M
    store_wifi_ssids: tuple[str, ...] = _parse_origins(DEFAULT_STORE_WIFI_SSIDS)

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
            admin_api_token=os.environ.get("ADMIN_API_TOKEN", DEFAULT_ADMIN_API_TOKEN),
            visit_verification_mode=os.environ.get(
                "VISIT_VERIFICATION_MODE", DEFAULT_VISIT_VERIFICATION_MODE
            ),
            store_geofence_lat=float(
                os.environ.get("STORE_GEOFENCE_LAT", DEFAULT_STORE_GEOFENCE_LAT)
            ),
            store_geofence_lng=float(
                os.environ.get("STORE_GEOFENCE_LNG", DEFAULT_STORE_GEOFENCE_LNG)
            ),
            store_geofence_radius_m=float(
                os.environ.get("STORE_GEOFENCE_RADIUS_M", DEFAULT_STORE_GEOFENCE_RADIUS_M)
            ),
            store_wifi_ssids=_parse_origins(
                os.environ.get("STORE_WIFI_SSIDS", DEFAULT_STORE_WIFI_SSIDS)
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
