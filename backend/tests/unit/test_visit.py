"""`app/visit.py`（フェーズ3-B 来店検証ストラテジ）の単体テスト。

DECISIONS.md #7「QRスキャン起動を基本、Wi-Fi/ジオフェンスは拡張余地・判定は差し替え
可能に」の実装検証。既定モード(qr)が現状と完全に同一挙動であることの回帰確認を含む。
"""
from __future__ import annotations

import math

import pytest

from app.config import Settings
from app.visit import (
    CompositeAndVerifier,
    GeofenceVerifier,
    QrVisitVerifier,
    WifiVerifier,
    haversine_distance_m,
    resolve_verifier,
)

EARTH_RADIUS_M = 6371000.0

# 目黒通り店（DECISIONS.md #4）付近の開発用ダミー座標（config.py の既定値と同一）。
STORE_LAT = 35.6203
STORE_LNG = 139.6883
STORE_RADIUS_M = 150.0


def _lat_offset_deg_for_distance(distance_m: float) -> float:
    """緯度方向（経度固定）に `distance_m` だけ離れた点の緯度オフセット(度)を返す。

    緯度方向（子午線に沿った移動）の大圏距離は `R * Δφ`（ラジアン）に厳密一致する
    （haversine公式で dλ=0 のとき a=sin^2(Δφ/2) となり c=|Δφ| に簡約されるため）。
    これを用いて「既知座標での手計算検証」の基準点を作る。
    """
    return math.degrees(distance_m / EARTH_RADIUS_M)


class TestHaversineDistanceM:
    """haversine距離計算そのものの手計算検証。"""

    def test_same_point_is_zero(self):
        assert haversine_distance_m(35.0, 139.0, 35.0, 139.0) == pytest.approx(0.0, abs=1e-6)

    def test_one_degree_longitude_at_equator_matches_known_circumference(self):
        # 赤道上での経度1度の大圏距離は 2πR/360 に厳密一致する既知の値。
        expected = 2 * math.pi * EARTH_RADIUS_M / 360
        actual = haversine_distance_m(0.0, 0.0, 0.0, 1.0)
        assert actual == pytest.approx(expected, rel=1e-9)

    def test_meridian_distance_matches_r_times_delta_phi(self):
        # 経度固定・緯度のみ0.01度離れた2点間の距離 = R * radians(0.01) の厳密値。
        delta_deg = 0.01
        expected = EARTH_RADIUS_M * math.radians(delta_deg)
        actual = haversine_distance_m(STORE_LAT, STORE_LNG, STORE_LAT + delta_deg, STORE_LNG)
        assert actual == pytest.approx(expected, rel=1e-9)


class TestGeofenceVerifier:
    """半径内=合格／半径外=不合格。境界を含めて検証する。"""

    def _verifier(self) -> GeofenceVerifier:
        return GeofenceVerifier(
            center_lat=STORE_LAT, center_lng=STORE_LNG, radius_m=STORE_RADIUS_M
        )

    def test_center_point_is_ok(self):
        result = self._verifier().verify(
            {"location_lat": STORE_LAT, "location_lng": STORE_LNG}
        )
        assert result.ok is True

    def test_within_radius_is_ok(self):
        # 半径150mの店舗から100m離れた地点（子午線方向）＝店内とみなす。
        delta = _lat_offset_deg_for_distance(100.0)
        result = self._verifier().verify(
            {"location_lat": STORE_LAT + delta, "location_lng": STORE_LNG}
        )
        assert result.ok is True

    def test_exactly_at_boundary_is_ok(self):
        # 境界（半径ちょうど）は合格側（<=）。
        delta = _lat_offset_deg_for_distance(STORE_RADIUS_M)
        result = self._verifier().verify(
            {"location_lat": STORE_LAT + delta, "location_lng": STORE_LNG}
        )
        assert result.ok is True

    def test_just_outside_radius_is_not_ok(self):
        delta = _lat_offset_deg_for_distance(STORE_RADIUS_M + 1.0)
        result = self._verifier().verify(
            {"location_lat": STORE_LAT + delta, "location_lng": STORE_LNG}
        )
        assert result.ok is False
        assert result.reason == "outside_geofence"

    def test_far_outside_is_not_ok(self):
        result = self._verifier().verify({"location_lat": 35.0, "location_lng": 135.0})
        assert result.ok is False
        assert result.reason == "outside_geofence"

    def test_missing_location_is_not_ok(self):
        result = self._verifier().verify({"location_lat": None, "location_lng": None})
        assert result.ok is False
        assert result.reason == "location_missing"

    def test_location_absent_from_session_dict_is_not_ok(self):
        result = self._verifier().verify({})
        assert result.ok is False
        assert result.reason == "location_missing"


class TestWifiVerifier:
    """一致=合格／不一致・欠如=不合格。"""

    def _verifier(self) -> WifiVerifier:
        return WifiVerifier(["Nitori-Free-Wifi", "Nitori-Guest-Wifi"])

    def test_matching_ssid_is_ok(self):
        result = self._verifier().verify({"wifi_ssid": "Nitori-Free-Wifi"})
        assert result.ok is True

    def test_non_matching_ssid_is_not_ok(self):
        result = self._verifier().verify({"wifi_ssid": "Some-Other-Wifi"})
        assert result.ok is False
        assert result.reason == "ssid_not_allowed"

    def test_missing_ssid_is_not_ok(self):
        result = self._verifier().verify({"wifi_ssid": None})
        assert result.ok is False
        assert result.reason == "ssid_missing"

    def test_empty_string_ssid_is_not_ok(self):
        result = self._verifier().verify({"wifi_ssid": ""})
        assert result.ok is False
        assert result.reason == "ssid_missing"

    def test_ssid_absent_from_session_dict_is_not_ok(self):
        result = self._verifier().verify({})
        assert result.ok is False
        assert result.reason == "ssid_missing"


class TestQrVisitVerifier:
    """既定検証: セッションが存在する時点で常に合格（位置情報の有無に依存しない）。"""

    def test_always_ok_regardless_of_location_signals(self):
        verifier = QrVisitVerifier()
        assert verifier.verify({}).ok is True
        assert verifier.verify({"location_lat": None}).ok is True
        assert verifier.verify({"wifi_ssid": "anything"}).ok is True


class TestCompositeAndVerifier:
    def test_all_ok_is_ok(self):
        composite = CompositeAndVerifier([QrVisitVerifier(), QrVisitVerifier()])
        assert composite.verify({}).ok is True

    def test_any_failure_short_circuits_to_not_ok(self):
        wifi = WifiVerifier(["Allowed-Ssid"])
        composite = CompositeAndVerifier([QrVisitVerifier(), wifi])
        result = composite.verify({"wifi_ssid": "Not-Allowed"})
        assert result.ok is False
        assert result.reason == "ssid_not_allowed"


class TestResolveVerifier:
    """モード文字列別のverifier合成（DECISIONS.md #7 差し替え可能性）。"""

    def _settings(self, **overrides) -> Settings:
        base = dict(
            visit_verification_mode="qr",
            store_geofence_lat=STORE_LAT,
            store_geofence_lng=STORE_LNG,
            store_geofence_radius_m=STORE_RADIUS_M,
            store_wifi_ssids=("Nitori-Free-Wifi",),
        )
        base.update(overrides)
        return Settings(**base)

    def test_default_qr_mode_returns_qr_verifier_only(self):
        settings = self._settings(visit_verification_mode="qr")
        verifier = resolve_verifier(settings)
        assert isinstance(verifier, QrVisitVerifier)

    def test_default_qr_mode_passes_without_any_location_signal(self):
        # 既定モード(qr)は位置なしセッションでも合格＝現状維持（無回帰の要）。
        settings = self._settings(visit_verification_mode="qr")
        verifier = resolve_verifier(settings)
        result = verifier.verify({"location_lat": None, "location_lng": None, "wifi_ssid": None})
        assert result.ok is True

    def test_qr_plus_geofence_mode_composes_both(self):
        settings = self._settings(visit_verification_mode="qr+geofence")
        verifier = resolve_verifier(settings)
        assert isinstance(verifier, CompositeAndVerifier)
        # 店内座標→合格
        inside = verifier.verify({"location_lat": STORE_LAT, "location_lng": STORE_LNG})
        assert inside.ok is True
        # 店外座標→不合格
        outside = verifier.verify({"location_lat": 35.0, "location_lng": 135.0})
        assert outside.ok is False
        # 位置なし→不合格（既定qrと違い、geofenceを追加した以上は必須になる）
        missing = verifier.verify({})
        assert missing.ok is False

    def test_qr_plus_wifi_mode_composes_both(self):
        settings = self._settings(visit_verification_mode="qr+wifi")
        verifier = resolve_verifier(settings)
        assert isinstance(verifier, CompositeAndVerifier)
        assert verifier.verify({"wifi_ssid": "Nitori-Free-Wifi"}).ok is True
        assert verifier.verify({"wifi_ssid": "Unknown"}).ok is False
        assert verifier.verify({}).ok is False

    def test_qr_plus_geofence_plus_wifi_mode_requires_all(self):
        settings = self._settings(visit_verification_mode="qr+geofence+wifi")
        verifier = resolve_verifier(settings)
        assert isinstance(verifier, CompositeAndVerifier)
        both_ok = verifier.verify(
            {
                "location_lat": STORE_LAT,
                "location_lng": STORE_LNG,
                "wifi_ssid": "Nitori-Free-Wifi",
            }
        )
        assert both_ok.ok is True
        only_geofence_ok = verifier.verify(
            {"location_lat": STORE_LAT, "location_lng": STORE_LNG, "wifi_ssid": "Unknown"}
        )
        assert only_geofence_ok.ok is False
        only_wifi_ok = verifier.verify(
            {"location_lat": 35.0, "location_lng": 135.0, "wifi_ssid": "Nitori-Free-Wifi"}
        )
        assert only_wifi_ok.ok is False

    def test_unknown_mode_token_falls_back_to_qr_required(self):
        # 設定ミス（未知トークン）でも安全側（QR必須）に倒れることを確認。
        settings = self._settings(visit_verification_mode="totally-unknown-mode")
        verifier = resolve_verifier(settings)
        assert isinstance(verifier, QrVisitVerifier)

    def test_geofence_only_mode_still_requires_qr(self):
        # "geofence" 単体指定でもQR起点セッションの存在チェックはAND合成に含まれる。
        settings = self._settings(visit_verification_mode="geofence")
        verifier = resolve_verifier(settings)
        assert isinstance(verifier, CompositeAndVerifier)
