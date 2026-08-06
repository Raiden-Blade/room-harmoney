"""`app/analytics.py`（フェーズ2-B1: A/B×KPI集計）の単体テスト。

推薦・経路と並ぶロジック層のテストとして、Store/FastAPIから独立した純粋関数
`compute_kpis` の算出式（分母0・片群欠損・空イベント含む）を検証する。
"""
from __future__ import annotations

import pytest

from app.analytics import compute_kpis
from app.experiment import CONTROL, TREATMENT


def _event(session_id, event_type, group, payload=None):
    return {
        "session_id": session_id,
        "event_type": event_type,
        "payload": payload or {},
        "experiment_group": group,
    }


def test_compute_kpis_with_no_events_returns_all_zero_without_error():
    result = compute_kpis([])

    for group in (TREATMENT, CONTROL):
        g = result["groups"][group]
        assert g["session_count"] == 0
        assert g["funnel"] == {
            "scanned": 0,
            "related_viewed": 0,
            "related_tapped": 0,
            "route_viewed": 0,
            "coordinate_viewed": 0,
            "chatbot_opened": 0,
        }
        assert g["rates"] == {
            "related_tap_rate": 0.0,
            "route_reach_rate": 0.0,
            "coordinate_view_rate": 0.0,
            "sub_passage_rate": 0.0,
        }
    assert result["diff"] == {
        "related_tap_rate": 0.0,
        "route_reach_rate": 0.0,
        "coordinate_view_rate": 0.0,
        "sub_passage_rate": 0.0,
    }
    assert result["pos_metrics"] is None
    assert "experiment_group" in result["note"] or "A/B" in result["note"]


def test_compute_kpis_funnel_rates_and_ab_diff_hand_calculated():
    """群別ファネル・率・diff を手計算値で検証する。

    treatment: T1(scan/related_view/related_tap/route_view via_sub_passage/coordinate_view/chatbot_open),
               T2(scan/related_view/route_view 非サブ通路), T3(scanのみ、related_view無し)
    control:   C1(scan/related_view/related_tap/route_view via_sub_passage), C2(scan/related_view)
    """
    events = [
        _event("T1", "session_start", TREATMENT),
        _event("T1", "qr_scan", TREATMENT),
        _event("T1", "related_view", TREATMENT),
        _event("T1", "related_tap", TREATMENT),
        _event("T1", "route_view", TREATMENT, {"via_sub_passage": True}),
        _event("T1", "coordinate_view", TREATMENT),
        _event("T1", "chatbot_open", TREATMENT),
        _event("T2", "session_start", TREATMENT),
        _event("T2", "qr_scan", TREATMENT),
        _event("T2", "related_view", TREATMENT),
        _event("T2", "route_view", TREATMENT, {"via_sub_passage": False}),
        _event("T3", "session_start", TREATMENT),
        _event("T3", "qr_scan", TREATMENT),
        _event("C1", "session_start", CONTROL),
        _event("C1", "qr_scan", CONTROL),
        _event("C1", "related_view", CONTROL),
        _event("C1", "related_tap", CONTROL),
        _event("C1", "route_view", CONTROL, {"via_sub_passage": True}),
        _event("C2", "session_start", CONTROL),
        _event("C2", "qr_scan", CONTROL),
        _event("C2", "related_view", CONTROL),
    ]

    result = compute_kpis(events)

    treatment = result["groups"][TREATMENT]
    assert treatment["session_count"] == 3
    assert treatment["funnel"] == {
        "scanned": 3,
        "related_viewed": 2,
        "related_tapped": 1,
        "route_viewed": 2,
        "coordinate_viewed": 1,
        "chatbot_opened": 1,
    }
    assert treatment["rates"]["related_tap_rate"] == pytest.approx(0.5)
    assert treatment["rates"]["route_reach_rate"] == pytest.approx(2 / 3)
    assert treatment["rates"]["coordinate_view_rate"] == pytest.approx(1 / 3)
    assert treatment["rates"]["sub_passage_rate"] == pytest.approx(0.5)  # 1/2 route_viewがサブ通路経由

    control = result["groups"][CONTROL]
    assert control["session_count"] == 2
    assert control["funnel"] == {
        "scanned": 2,
        "related_viewed": 2,
        "related_tapped": 1,
        "route_viewed": 1,
        "coordinate_viewed": 0,
        "chatbot_opened": 0,
    }
    assert control["rates"]["related_tap_rate"] == pytest.approx(0.5)
    assert control["rates"]["route_reach_rate"] == pytest.approx(0.5)
    assert control["rates"]["coordinate_view_rate"] == pytest.approx(0.0)
    assert control["rates"]["sub_passage_rate"] == pytest.approx(1.0)  # 1/1 route_viewがサブ通路経由

    diff = result["diff"]
    assert diff["related_tap_rate"] == pytest.approx(0.0)
    assert diff["route_reach_rate"] == pytest.approx(2 / 3 - 0.5)
    assert diff["coordinate_view_rate"] == pytest.approx(1 / 3 - 0.0)
    assert diff["sub_passage_rate"] == pytest.approx(0.5 - 1.0)


def test_compute_kpis_zero_denominator_yields_zero_rate_not_error():
    """related_view が1件も無いセッション群では related_tap_rate は0（例外にならない）。"""
    events = [
        _event("T1", "session_start", TREATMENT),
        _event("T1", "qr_scan", TREATMENT),
        # related_view/related_tap 無し
    ]

    result = compute_kpis(events)

    assert result["groups"][TREATMENT]["rates"]["related_tap_rate"] == 0.0
    assert result["groups"][TREATMENT]["rates"]["sub_passage_rate"] == 0.0  # route_view無しでも0


def test_compute_kpis_missing_one_group_entirely_still_computes_diff():
    """control 側のイベントが1件も無い場合でも例外にならず、diffは treatment - 0 になる。"""
    events = [
        _event("T1", "session_start", TREATMENT),
        _event("T1", "qr_scan", TREATMENT),
        _event("T1", "related_view", TREATMENT),
        _event("T1", "related_tap", TREATMENT),
    ]

    result = compute_kpis(events)

    assert result["groups"][CONTROL]["session_count"] == 0
    assert result["groups"][CONTROL]["rates"]["related_tap_rate"] == 0.0
    assert result["diff"]["related_tap_rate"] == pytest.approx(1.0 - 0.0)


def test_compute_kpis_via_sub_passage_fallback_from_legacy_sub_passage_count():
    """`via_sub_passage` キーが無い古い route_view payload でも `sub_passage_count` から
    サブ通路経由の有無を導出できる（後方互換）。"""
    events = [
        _event("T1", "session_start", TREATMENT),
        _event("T1", "route_view", TREATMENT, {"sub_passage_count": 2}),
        _event("T2", "session_start", TREATMENT),
        _event("T2", "route_view", TREATMENT, {"sub_passage_count": 0}),
    ]

    result = compute_kpis(events)

    assert result["groups"][TREATMENT]["rates"]["sub_passage_rate"] == pytest.approx(0.5)


def test_compute_kpis_ignores_events_with_unknown_experiment_group():
    """`experiment_group` が treatment/control のどちらでもない（None等）イベントは集計対象外。"""
    events = [
        _event("X1", "session_start", None),
        _event("X1", "qr_scan", None),
        _event("T1", "session_start", TREATMENT),
    ]

    result = compute_kpis(events)

    assert result["groups"][TREATMENT]["session_count"] == 1
    assert result["groups"][CONTROL]["session_count"] == 0


def test_compute_kpis_pos_metrics_returns_values_and_diff_when_provided():
    pos_metrics = {
        TREATMENT: {
            "co_purchase_rate": 0.3,
            "items_per_purchase": 2.5,
            "spend_per_customer": 6000,
        },
        CONTROL: {
            "co_purchase_rate": 0.2,
            "items_per_purchase": 2.0,
            "spend_per_customer": 5000,
        },
    }

    result = compute_kpis([], pos_metrics=pos_metrics)

    pos = result["pos_metrics"]
    assert pos is not None
    assert pos["groups"][TREATMENT]["co_purchase_rate"] == pytest.approx(0.3)
    assert pos["groups"][CONTROL]["co_purchase_rate"] == pytest.approx(0.2)
    assert pos["diff"]["co_purchase_rate"] == pytest.approx(0.1)
    assert pos["diff"]["items_per_purchase"] == pytest.approx(0.5)
    assert pos["diff"]["spend_per_customer"] == pytest.approx(1000)


def test_compute_kpis_pos_metrics_returns_none_when_not_provided():
    assert compute_kpis([], pos_metrics=None)["pos_metrics"] is None
    assert compute_kpis([], pos_metrics={})["pos_metrics"] is None


def test_compute_kpis_pos_metrics_partial_group_yields_none_diff_for_missing_metric():
    """片群のみ値がある指標は diff を None（N/A）にする（欠損に強くする）。"""
    pos_metrics = {
        TREATMENT: {"co_purchase_rate": 0.3},
        CONTROL: {},
    }

    result = compute_kpis([], pos_metrics=pos_metrics)

    pos = result["pos_metrics"]
    assert pos["groups"][TREATMENT]["co_purchase_rate"] == pytest.approx(0.3)
    assert pos["groups"][CONTROL]["co_purchase_rate"] is None
    assert pos["diff"]["co_purchase_rate"] is None
    assert pos["diff"]["items_per_purchase"] is None
