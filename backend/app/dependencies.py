"""FastAPI の依存性注入（Depends）定義。

責務分離・差し替え可能性（DESIGN.md 設計原則／DECISIONS.md #7）のため、以下をすべて
`Depends` 経由で提供する。結合テストは `app.dependency_overrides` でこれらを
上書きしてDB隔離・決定的な実験群割付・（将来のWi-Fi/ジオフェンス等）来店判定ロジック
差し替えを検証できる。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from fastapi import Depends, Query

from recommender import RecommenderInterface
from recommender.hybrid import HybridRecommender
from routing import RouteGraphBuilder

from .config import Settings, get_settings
from .errors import ApiError
from .experiment import ExperimentAssigner
from .repositories import (
    CoordinateRepository,
    ProductRepository,
    QrRepository,
    StoreMapRepository,
)
from .store import Store


# -- データ参照層（読み取り専用。data/ の実データから構築するシングルトン） -----------
@lru_cache
def get_product_repo() -> ProductRepository:
    return ProductRepository.from_data_dir()


@lru_cache
def get_qr_repo() -> QrRepository:
    return QrRepository.from_data_dir()


@lru_cache
def get_coordinate_repo() -> CoordinateRepository:
    return CoordinateRepository.from_data_dir()


@lru_cache
def get_store_map_repo() -> StoreMapRepository:
    return StoreMapRepository.from_data_dir()


# -- ロジック層（B1推薦／B2経路。RecommenderInterface として差し替え可能） -------------
@lru_cache
def get_recommender() -> RecommenderInterface:
    return HybridRecommender.from_data_dir()


@lru_cache
def get_route_builder() -> RouteGraphBuilder:
    from dataio import DEFAULT_DATA_DIR

    return RouteGraphBuilder.from_store_map_file(DEFAULT_DATA_DIR / "store_map.json")


# -- 永続化層（sessions/events。テストは dependency_overrides で隔離DBに差し替える） ---
@lru_cache
def get_store() -> Store:
    settings = get_settings()
    return Store(settings.database_path)


# -- 実験群割付（乱数生成器を注入可能。テストはシード固定の実装に差し替える） -----------
@lru_cache
def get_experiment_assigner() -> ExperimentAssigner:
    settings = get_settings()
    return ExperimentAssigner(
        mode=settings.experiment_group_mode, ratio=settings.experiment_group_ratio
    )


# -- 来店ロック（9章 非機能要件 / DECISIONS.md #7） -------------------------------------
# 判定ロジックを Depends にすることで差し替え可能にする（将来 Wi-Fi/ジオフェンス判定を
# 追加する場合も、この関数を別実装に差し替えるだけでよい設計。テストは
# `app.dependency_overrides[require_active_session]` で丸ごと差し替えることもできる）。
def require_active_session(
    session_id: Optional[str] = Query(
        default=None, description="来店セッションID（POST /api/session で発行）"
    ),
    store: Store = Depends(get_store),
) -> dict[str, Any]:
    """有効な来店セッション（QR起点で開始済み）が無ければ 409 で中核機能をロックする。

    9章「来店時のみ作動の担保」/ AC-5: 有効な店内QR起点セッションが無い場合は
    中核機能（関連表示・ルート）をロックし、店頭QRの読取を促す。
    """
    if not session_id:
        raise ApiError(
            status_code=409,
            code="VISIT_LOCK_REQUIRED",
            message="この機能を利用するには、店頭のQRコードを読み取って来店セッションを開始してください。",
        )
    session = store.get_session(session_id)
    if session is None:
        raise ApiError(
            status_code=409,
            code="VISIT_LOCK_REQUIRED",
            message="有効な来店セッションが見つかりません。店頭のQRコードを読み取り直してください。",
        )
    return session
