"""A/B×KPI集計ロジック（10章 計測・ログ設計／12章 KPI／フェーズ2-B1）。

入出力がプレーンな `dict`/`list` の**純粋関数**として実装し、Store/FastAPI から独立して
単体テストできるようにする（責務分離：データ層(Store)／ロジック層(本モジュール)／API層(routers)）。

因果の扱いについての注記（10章）:
本モジュールは `experiment_group`（`treatment`=Room Harmony利用群 / `control`=非利用群）
別の単純な記述統計（件数・率・差分）を返すのみであり、これは **A/B割付が正しく機能して
いること（=両群が交換可能であること）を前提**にした比較である。割付が崩れている場合や、
セッション属性に系統的な差がある場合は、単純な group 間の差分（`diff`）を因果効果として
解釈できない。本格的な効果検証では別途マッチング/差の差分析（DiD）等を行うこと。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from .experiment import CONTROL, TREATMENT

# 対象群（10章: Room Harmony利用群 / 非利用群の2群）。experiment_group がこれ以外
# （None・不正値）のイベントは集計対象外とする（テストの決定性・POS突合の一貫性のため）。
GROUPS = (TREATMENT, CONTROL)

# ファネル集計に使うイベント種別（10章のイベント種別のうち計測対象のもの）。
_FUNNEL_EVENT_TYPES = (
    "session_start",
    "qr_scan",
    "related_view",
    "related_tap",
    "route_view",
    "coordinate_view",
    "chatbot_open",
)

# POS突合スロットで扱う指標キー（10章「計測に紐づけるKPI」）。
POS_METRIC_KEYS = ("co_purchase_rate", "items_per_purchase", "spend_per_customer")

CAUSAL_NOTE = (
    "この集計は experiment_group（treatment=Room Harmony利用群 / control=非利用群）による"
    "A/B割付を前提とした群間比較です。利用有無の単純な事後比較（相関）ではなく、"
    "割付済みの2群の差分（diff）として解釈してください。"
)


def _rate(numerator: int, denominator: int) -> float:
    """分母0を0.0として扱う安全な割り算（None回避）。"""
    return numerator / denominator if denominator else 0.0


def _empty_group_result() -> dict[str, Any]:
    funnel = {
        "scanned": 0,
        "related_viewed": 0,
        "related_tapped": 0,
        "route_viewed": 0,
        "coordinate_viewed": 0,
        "chatbot_opened": 0,
    }
    rates = {
        "related_tap_rate": 0.0,
        "route_reach_rate": 0.0,
        "coordinate_view_rate": 0.0,
        "sub_passage_rate": 0.0,
    }
    return {"session_count": 0, "funnel": funnel, "rates": rates}


def _via_sub_passage(payload: dict[str, Any]) -> bool:
    """route_view payload からサブ通路経由の有無を判定する。

    `route.py` は `via_sub_passage`（bool）を payload に含める（本フェーズでの補強）。
    後方互換のため、それが無い古いレコードは `sub_passage_count`（既存フィールド）から
    導出する。
    """
    if "via_sub_passage" in payload:
        return bool(payload.get("via_sub_passage"))
    return bool(payload.get("sub_passage_count", 0))


def compute_kpis(
    events: list[dict[str, Any]],
    pos_metrics: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """イベント配列から experiment_group 別KPI・ファネル・A/B差分を算出する。

    Args:
        events: `Store.list_events()` と同形の dict のリスト
            （`session_id, event_type, payload(dict), experiment_group, timestamp`）。
        pos_metrics: POS突合の群別指標（`{"treatment": {...}, "control": {...}}`）。
            各群の値は `co_purchase_rate` / `items_per_purchase` / `spend_per_customer`。
            未指定・空の場合は `pos_metrics` キーに `None`（N/A）を返す。

    Returns:
        群別KPI（`groups`）・率のA/B差分（`diff`）・POS突合スロット（`pos_metrics`）・
        因果解釈の注記（`note`）を持つ dict。
    """
    # 群 × イベント種別 → セッションID集合
    sessions_by_type: dict[str, dict[str, set]] = {
        g: defaultdict(set) for g in GROUPS
    }
    route_view_sessions: dict[str, set] = {g: set() for g in GROUPS}
    sub_passage_sessions: dict[str, set] = {g: set() for g in GROUPS}

    for event in events:
        group = event.get("experiment_group")
        if group not in GROUPS:
            # 未知/欠損の群は対象外（例: セッション作成前の異常データ等）。
            continue
        event_type = event.get("event_type")
        session_id = event.get("session_id")
        if event_type in _FUNNEL_EVENT_TYPES and session_id is not None:
            sessions_by_type[group][event_type].add(session_id)

        if event_type == "route_view" and session_id is not None:
            route_view_sessions[group].add(session_id)
            payload = event.get("payload") or {}
            if _via_sub_passage(payload):
                sub_passage_sessions[group].add(session_id)

    groups_result: dict[str, Any] = {}
    for group in GROUPS:
        by_type = sessions_by_type[group]
        scanned = by_type["qr_scan"] | by_type["session_start"]
        related_viewed = by_type["related_view"]
        related_tapped = by_type["related_tap"]
        route_viewed = by_type["route_view"]
        coordinate_viewed = by_type["coordinate_view"]
        chatbot_opened = by_type["chatbot_open"]

        funnel = {
            "scanned": len(scanned),
            "related_viewed": len(related_viewed),
            "related_tapped": len(related_tapped),
            "route_viewed": len(route_viewed),
            "coordinate_viewed": len(coordinate_viewed),
            "chatbot_opened": len(chatbot_opened),
        }
        rates = {
            "related_tap_rate": _rate(len(related_tapped), len(related_viewed)),
            "route_reach_rate": _rate(len(route_viewed), len(scanned)),
            "coordinate_view_rate": _rate(len(coordinate_viewed), len(scanned)),
            "sub_passage_rate": _rate(
                len(sub_passage_sessions[group]), len(route_view_sessions[group])
            ),
        }
        groups_result[group] = {
            "session_count": len(by_type["session_start"]),
            "funnel": funnel,
            "rates": rates,
        }

    if not groups_result:  # pragma: no cover - GROUPS は常に非空
        groups_result = {g: _empty_group_result() for g in GROUPS}

    # A/B差分（treatment - control）。各群の rates キー集合は揃っているので
    # TREATMENT 側のキーを基準にすればよい。
    diff = {
        key: groups_result[TREATMENT]["rates"][key] - groups_result[CONTROL]["rates"][key]
        for key in groups_result[TREATMENT]["rates"]
    }

    return {
        "groups": groups_result,
        "diff": diff,
        "pos_metrics": _compute_pos_block(pos_metrics),
        "note": CAUSAL_NOTE,
    }


def _compute_pos_block(pos_metrics: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """POS突合スロット（併売率/買上点数/客単価）を群別値＋diffの形にまとめる。

    `pos_metrics` が未指定/空、または対象群のデータが全く無い場合は `None`（N/A）を返す。
    片方の群にしか値が無い指標は、その指標の `diff` のみ `None` にする（欠損に強くする）。
    """
    if not pos_metrics:
        return None

    groups: dict[str, dict[str, Optional[float]]] = {}
    for group in GROUPS:
        group_data = pos_metrics.get(group) or {}
        groups[group] = {key: group_data.get(key) for key in POS_METRIC_KEYS}

    diff: dict[str, Optional[float]] = {}
    for key in POS_METRIC_KEYS:
        treatment_value = groups[TREATMENT].get(key)
        control_value = groups[CONTROL].get(key)
        if treatment_value is None or control_value is None:
            diff[key] = None
        else:
            diff[key] = treatment_value - control_value

    return {"groups": groups, "diff": diff}
