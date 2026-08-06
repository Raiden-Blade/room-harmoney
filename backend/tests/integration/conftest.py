"""結合テスト共通フィクスチャ（G2 API結合ゲート）。

- `isolated_store` / `client`: `tmp_path` 配下の隔離SQLiteファイルを使う `Store` に
  差し替え、本番/開発DB（`data/room_harmony.db`）を一切汚さないようにする。
- `client` は実験群割付をシード固定の `ExperimentAssigner` に差し替え、
  テストを決定的にする（AC-4 の experiment_group 付与検証のため）。
"""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_experiment_assigner, get_store
from app.experiment import ExperimentAssigner
from app.main import app
from app.store import Store

# テストの再現性のための固定シード。DECISIONS.md #7
# 「来店判定の要件水準」との整合で、割付ロジック自体は差し替え可能な依存として
# 実装しているため、テストでは決定的な実装に丸ごと差し替える。
_TEST_SEED = 20260806


@pytest.fixture()
def isolated_store(tmp_path) -> Store:
    db_path = tmp_path / "test_room_harmony.db"
    return Store(db_path)


@pytest.fixture()
def client(isolated_store: Store):
    app.dependency_overrides[get_store] = lambda: isolated_store
    app.dependency_overrides[get_experiment_assigner] = lambda: ExperimentAssigner(
        rng=random.Random(_TEST_SEED)
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def store(isolated_store: Store) -> Store:
    """`client` 経由の操作結果をDB側から直接アサートするためのアクセサ。"""
    return isolated_store


@pytest.fixture()
def active_session(client) -> dict:
    """有効な来店セッション（QR起点）を1件作成し、レスポンスをそのまま返す。

    来店ロック対象のエンドポイント（recommendations / route）を検証するテストの
    前提セットアップとして使う。
    """
    response = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
    assert response.status_code == 200
    return response.json()
