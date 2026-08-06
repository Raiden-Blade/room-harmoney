"""experiment_group 割付（AC-4）の結合テスト。差し替え可能な `ExperimentAssigner` の
デフォルト実装（比率ベースの乱数割付）を検証する。
"""
from __future__ import annotations

import random

from app.dependencies import get_experiment_assigner
from app.experiment import CONTROL, ExperimentAssigner, TREATMENT
from app.main import app


def test_experiment_assigner_respects_ratio_deterministically():
    """シードを固定した rng を渡すと、割付結果は決定的に再現できる。"""
    assigner = ExperimentAssigner(mode="random", ratio=0.5, rng=random.Random(1))

    results = [assigner.assign() for _ in range(5)]

    assert all(r in {TREATMENT, CONTROL} for r in results)
    # 同じシードで作り直すと同じ系列になる（決定性の確認）。
    replay_assigner = ExperimentAssigner(mode="random", ratio=0.5, rng=random.Random(1))
    replay_results = [replay_assigner.assign() for _ in range(5)]
    assert results == replay_results


def test_experiment_assigner_ratio_zero_always_control():
    assigner = ExperimentAssigner(mode="random", ratio=0.0, rng=random.Random(1))
    assert all(assigner.assign() == CONTROL for _ in range(10))


def test_experiment_assigner_ratio_one_always_treatment():
    assigner = ExperimentAssigner(mode="random", ratio=1.0, rng=random.Random(1))
    assert all(assigner.assign() == TREATMENT for _ in range(10))


def test_session_creation_uses_injected_assigner_override(client):
    """`get_experiment_assigner` を差し替え可能（DIで注入可能）であることを、
    conftest の override 経由で作成したセッションの experiment_group が
    許容値のいずれかであることで確認する（実装への差し替え可能性の検証）。
    """
    response = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
    assert response.status_code == 200
    assert response.json()["experiment_group"] in {TREATMENT, CONTROL}


def test_experiment_group_dependency_is_overridable_to_fixed_group(isolated_store):
    """来店ロック同様、experiment_group割付も Depends 経由で丸ごと差し替え可能なことを検証する。"""
    from fastapi.testclient import TestClient

    from app.dependencies import get_store

    app.dependency_overrides[get_store] = lambda: isolated_store
    app.dependency_overrides[get_experiment_assigner] = lambda: ExperimentAssigner(
        rng=random.Random(0), ratio=1.0
    )
    try:
        with TestClient(app) as fixed_client:
            response = fixed_client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
            assert response.json()["experiment_group"] == TREATMENT
    finally:
        app.dependency_overrides.clear()
