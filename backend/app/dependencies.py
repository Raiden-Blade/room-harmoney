"""FastAPI の依存性注入（Depends）定義。

責務分離・差し替え可能性（DESIGN.md 設計原則／DECISIONS.md #7）のため、以下をすべて
`Depends` 経由で提供する。結合テストは `app.dependency_overrides` でこれらを
上書きしてDB隔離・決定的な実験群割付・（将来のWi-Fi/ジオフェンス等）来店判定ロジック
差し替えを検証できる。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from fastapi import Depends, Header, Query

from recommender import RecommenderInterface
from recommender.personalized import PersonalizedRecommender
from routing import RouteGraphBuilder

from dataio import DEFAULT_DATA_DIR, load_json_dict

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
from .visit import VisitVerifier, resolve_verifier


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
# フェーズ3-A（DECISIONS.md 改訂#5-A）: `PersonalizedRecommender` は内部で
# `HybridRecommender`（base）を合成しているだけで、`member_id` 未指定の呼び出しは
# base と完全に同一の結果を返す後方互換実装。よって既存の呼び出し（member_id無し）は
# 挙動を一切変えないまま、任意で会員パーソナライズが使えるようになる。
@lru_cache
def get_recommender() -> RecommenderInterface:
    return PersonalizedRecommender.from_data_dir()


@lru_cache
def get_route_builder() -> RouteGraphBuilder:
    from dataio import DEFAULT_DATA_DIR

    return RouteGraphBuilder.from_store_map_file(DEFAULT_DATA_DIR / "store_map.json")


# -- 永続化層（sessions/events。テストは dependency_overrides で隔離DBに差し替える） ---
@lru_cache
def get_store() -> Store:
    settings = get_settings()
    return Store(settings.database_path)


# -- POS突合データ（フェーズ2-B1 KPI集計。任意データ・欠損時は None＝N/A） --------------
# `lru_cache` を付けない: 実運用でPOS集計値を随時更新する運用を想定し、リクエストの都度
# 最新の `data/pos_metrics.json` を読む（ファイルI/Oは軽量なため許容）。結合テストでは
# `app.dependency_overrides[get_pos_metrics]` で群別の固定値/Noneに差し替えて検証する。
def get_pos_metrics() -> Optional[dict[str, Any]]:
    data = load_json_dict("pos_metrics.json", default={}, data_dir=DEFAULT_DATA_DIR)
    return data or None


# -- 実験群割付（乱数生成器を注入可能。テストはシード固定の実装に差し替える） -----------
@lru_cache
def get_experiment_assigner() -> ExperimentAssigner:
    settings = get_settings()
    return ExperimentAssigner(
        mode=settings.experiment_group_mode, ratio=settings.experiment_group_ratio
    )


# -- 来店ロック（9章 非機能要件 / DECISIONS.md #7） -------------------------------------
# 判定ロジックを Depends にすることで差し替え可能にする（フェーズ3-B: Wi-Fi/ジオフェンス
# 判定を追加する場合も、`VisitVerifier` の実装を差し替えるだけでよい設計。テストは
# `app.dependency_overrides[require_active_session]`（丸ごと差し替え）や
# `app.dependency_overrides[get_visit_verifier]`（判定ロジックのみ差し替え）、
# `app.dependency_overrides[get_settings]`（`VISIT_VERIFICATION_MODE` 差し替え）で
# 検証できる）。
def get_visit_verifier(settings: Settings = Depends(get_settings)) -> VisitVerifier:
    """`VISIT_VERIFICATION_MODE`（既定 "qr"）から来店検証ストラテジを合成する。"""
    return resolve_verifier(settings)


def require_active_session(
    session_id: Optional[str] = Query(
        default=None, description="来店セッションID（POST /api/session で発行）"
    ),
    store: Store = Depends(get_store),
    verifier: VisitVerifier = Depends(get_visit_verifier),
) -> dict[str, Any]:
    """有効な来店セッション（QR起点で開始済み）が無ければ 409 で中核機能をロックする。

    9章「来店時のみ作動の担保」/ AC-5: 有効な店内QR起点セッションが無い場合は
    中核機能（関連表示・ルート）をロックし、店頭QRの読取を促す。

    フェーズ3-B: 既定モード（"qr"）では `verifier` は常に合格するため挙動は従来と
    完全に同一。拡張モード（"qr+geofence"/"qr+wifi"等）では、セッションに紐づく
    位置/SSIDシグナルの検証にも失敗した場合、`VISIT_NOT_VERIFIED` で409を返す。
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
    result = verifier.verify(session)
    if not result.ok:
        raise ApiError(
            status_code=409,
            code="VISIT_NOT_VERIFIED",
            message=(
                "来店確認ができませんでした。店舗内でWi-Fi/位置情報を有効にするか、"
                "店頭のQRコードを読み取り直してください。"
            ),
        )
    return session


# -- 管理系認証（17章「管理系（データ投入・ダッシュボード）は認証必須」） ------------------
# 前提（未確定事項寄りの実装判断・コメントで明記）: 本要件は「認証必須」とのみ規定し、
# 認証方式までは指定していない。管理画面へのログインUI等は本フェーズのスコープ外
# （KPI集計APIのみ）のため、単純な共有トークン（`X-Admin-Token` ヘッダー）照合を採用する。
# パスワード入力・セッション管理は行わない。実運用ではリバースプロキシでのIP制限等と
# 組み合わせる想定。
def require_admin(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    settings: Settings = Depends(get_settings),
) -> None:
    """`X-Admin-Token` ヘッダーが `Settings.admin_api_token` と一致しなければ401にする。"""
    if not x_admin_token or x_admin_token != settings.admin_api_token:
        raise ApiError(
            status_code=401,
            code="ADMIN_UNAUTHORIZED",
            message="管理系APIの認証に失敗しました。X-Admin-Token ヘッダーを正しく指定してください。",
        )
