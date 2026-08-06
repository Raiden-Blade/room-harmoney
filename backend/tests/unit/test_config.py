"""`app/config.py`（環境変数からの設定読み込み）の単体テスト。

QA G3 G-G3-7 申し送り対応の回帰テスト: CORS許可オリジンが
`CORS_ALLOW_ORIGINS`（カンマ区切り）環境変数から読み込め、未設定時は
Vite dev（5173）と `vite preview`（4173）の両方を localhost/127.0.0.1 で
既定許可することを検証する。
"""
from __future__ import annotations

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def _clean_cors_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """他テストの環境変数汚染を避けるため、CORS_ALLOW_ORIGINS を毎回未設定にする。"""
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)


def test_default_cors_allow_origins_include_dev_and_preview_ports() -> None:
    """既定値（env未設定）は Vite dev(5173) と vite preview(4173) を
    localhost/127.0.0.1 の両方で含む（QA G3 G-G3-7: previewでの検証がCORSで
    ブロックされていた問題の回帰防止）。"""
    settings = Settings.from_env()

    assert settings.cors_allow_origins == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    )


def test_cors_allow_origins_read_from_env_comma_separated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`CORS_ALLOW_ORIGINS` 環境変数（カンマ区切り、前後空白は除去）から読み込める。"""
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        " https://roomharmony.example.com , https://admin.roomharmony.example.com ",
    )

    settings = Settings.from_env()

    assert settings.cors_allow_origins == (
        "https://roomharmony.example.com",
        "https://admin.roomharmony.example.com",
    )


def test_cors_allow_origins_ignores_empty_segments(monkeypatch: pytest.MonkeyPatch) -> None:
    """末尾カンマ等で生じる空要素は無視する。"""
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,,")

    settings = Settings.from_env()

    assert settings.cors_allow_origins == ("http://localhost:5173",)
