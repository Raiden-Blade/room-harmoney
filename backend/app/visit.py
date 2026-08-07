"""来店検証ストラテジ（フェーズ3-B / DECISIONS.md #7・要件9章「来店時のみ作動の担保」）。

要件9章は「補強策として店舗Wi-Fi/ジオフェンス判定を追加可能な設計にしておく」とし、
DECISIONS.md #7 は「QRスキャン起動を基本とする。Wi-Fi/ジオフェンスは拡張余地として
設計（今回は実装しない）。判定ロジックは差し替え可能に」と確定している。

このモジュールはその「差し替え可能な来店判定ロジック」の実体を提供する。

- 既定モード（`VISIT_VERIFICATION_MODE=qr`）: `QrVisitVerifier` のみを使う。
  有効なQR起点セッションが存在すれば常に合格＝**現状（フェーズ3-B以前）と完全に同一挙動**。
  位置情報(lat/lng)・SSIDは一切参照しない。
- 拡張モード（`qr+geofence` / `qr+wifi` / `qr+geofence+wifi`）: QR検証に加えて、
  ジオフェンス／Wi-Fi SSID検証を **AND合成**する（すべて合格して初めて来店とみなす）。
  これはオプトインの追加検証であり、既定モードの挙動には一切影響しない。

プライバシー（9章「ログはセッション単位で匿名」）: 位置情報・SSIDは来店判定にのみ使用し、
`events`（効果ログ）には一切保存しない。判定用に `sessions` テーブルへ保持するのみ。
精密測位（GPSの高精度・継続測位等）は行わない前提を維持し、ここではセッション開始時に
一度だけ報告された座標/SSIDでの簡易判定にとどめる。
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .config import Settings

# 地球の平均半径(m)。haversine距離計算に使用（測地系の厳密な楕円体補正は行わない簡易判定
# という前提。来店/非来店の粗い判定には十分な精度）。
EARTH_RADIUS_M = 6371000.0

# モード文字列の区切り文字（例: "qr+geofence"）。
_MODE_SEPARATOR = "+"


def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """2点間（緯度経度）の大圏距離をメートルで返す（haversine公式）。"""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c


@dataclass(frozen=True)
class VisitVerificationResult:
    """来店検証の結果。`reason` は内部診断用の識別子で、events等の外部ログには出さない。"""

    ok: bool
    reason: Optional[str] = None


class VisitVerifier(ABC):
    """来店検証ストラテジの抽象基底（差し替え可能にするためのインターフェース）。"""

    @abstractmethod
    def verify(self, session: dict[str, Any]) -> VisitVerificationResult:
        """`Store.get_session` が返すセッション行を受け取り、来店として合格かを判定する。"""


class QrVisitVerifier(VisitVerifier):
    """既定の来店検証: 有効なQR起点セッションが存在すれば合格する（現状ロジック）。

    `session` は `require_active_session` 側で「存在するセッション」が既に確定した状態で
    渡ってくる（session_idが未指定/該当なしの場合は409を送出済み）ため、ここでは常に合格。
    """

    def verify(self, session: dict[str, Any]) -> VisitVerificationResult:
        return VisitVerificationResult(ok=True)


class GeofenceVerifier(VisitVerifier):
    """店舗の中心座標＋半径(m)で、セッションに紐づく報告位置が店内かを判定する。"""

    def __init__(self, center_lat: float, center_lng: float, radius_m: float):
        self._center_lat = center_lat
        self._center_lng = center_lng
        self._radius_m = radius_m

    def verify(self, session: dict[str, Any]) -> VisitVerificationResult:
        lat = session.get("location_lat")
        lng = session.get("location_lng")
        if lat is None or lng is None:
            return VisitVerificationResult(ok=False, reason="location_missing")
        distance_m = haversine_distance_m(lat, lng, self._center_lat, self._center_lng)
        if distance_m <= self._radius_m:
            return VisitVerificationResult(ok=True)
        return VisitVerificationResult(ok=False, reason="outside_geofence")


class WifiVerifier(VisitVerifier):
    """許可SSIDリストに、セッションの報告SSIDが一致するかを判定する。"""

    def __init__(self, allowed_ssids: Iterable[str]):
        self._allowed = {ssid.strip() for ssid in allowed_ssids if ssid and ssid.strip()}

    def verify(self, session: dict[str, Any]) -> VisitVerificationResult:
        ssid = session.get("wifi_ssid")
        if not ssid:
            return VisitVerificationResult(ok=False, reason="ssid_missing")
        if ssid in self._allowed:
            return VisitVerificationResult(ok=True)
        return VisitVerificationResult(ok=False, reason="ssid_not_allowed")


class CompositeAndVerifier(VisitVerifier):
    """複数の `VisitVerifier` をAND合成する（すべて合格して初めて合格＝来店と判定）。"""

    def __init__(self, verifiers: Iterable[VisitVerifier]):
        self._verifiers = list(verifiers)

    def verify(self, session: dict[str, Any]) -> VisitVerificationResult:
        for verifier in self._verifiers:
            result = verifier.verify(session)
            if not result.ok:
                return result
        return VisitVerificationResult(ok=True)


def resolve_verifier(settings: Settings) -> VisitVerifier:
    """`settings.visit_verification_mode` から `VisitVerifier` を合成する。

    - "qr"（既定）: `QrVisitVerifier` のみ。既存の来店ロックと完全に同一挙動。
    - "qr+geofence" / "qr+wifi" / "qr+geofence+wifi": QR検証に加え、対応する追加検証を
      AND合成する（"+" 区切り、順序は問わない）。
    - 未知のモード片は無視せず `QrVisitVerifier` を補って安全側（QR必須）にフォールバック
      する（設定ミスで来店ロックが無効化される事故を避けるため）。
    """
    parts = [
        part.strip()
        for part in settings.visit_verification_mode.split(_MODE_SEPARATOR)
        if part.strip()
    ]
    if not parts:
        parts = ["qr"]

    verifiers: list[VisitVerifier] = []
    has_qr = False
    for part in parts:
        if part == "qr":
            has_qr = True
            verifiers.append(QrVisitVerifier())
        elif part == "geofence":
            verifiers.append(
                GeofenceVerifier(
                    center_lat=settings.store_geofence_lat,
                    center_lng=settings.store_geofence_lng,
                    radius_m=settings.store_geofence_radius_m,
                )
            )
        elif part == "wifi":
            verifiers.append(WifiVerifier(settings.store_wifi_ssids))
        # 未知トークンは静かに無視する（下でQR必須を保証する）。

    if not has_qr:
        # "geofence" や "wifi" 単体指定・未知のモード文字列でもQR起点セッションの存在
        # チェック自体は常に必須にする（安全側フォールバック）。
        verifiers.insert(0, QrVisitVerifier())

    if len(verifiers) == 1:
        return verifiers[0]
    return CompositeAndVerifier(verifiers)
