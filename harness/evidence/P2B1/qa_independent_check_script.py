"""QA独立検算スクリプト（G-P2B1-4/5/6/7）。
実装コードは一切変更しない。TestClient + 隔離tmp DBで、自分で設計したイベント列を
投入し、/api/admin/kpi の応答を手計算値と突合する。
"""
from __future__ import annotations

import json
import random
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(r"C:\Users\haseg\OneDrive\Documents\ニトリ制作物\room-harmony\backend")
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.dependencies import (  # noqa: E402
    get_experiment_assigner,
    get_pos_metrics,
    get_settings,
    get_store,
)
from app.experiment import CONTROL, ExperimentAssigner, TREATMENT  # noqa: E402
from app.main import app  # noqa: E402
from app.store import Store  # noqa: E402

ADMIN_TOKEN = "qa-independent-token-xyz789"

results = {"pass": [], "fail": []}


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        results["pass"].append(name)
        print(f"[PASS] {name} {detail}")
    else:
        results["fail"].append(name + " " + detail)
        print(f"[FAIL] {name} {detail}")


def force_group_sequence(groups):
    """session作成順にgroupsを順番に割り当てる決定的Assignerのフェイク。"""
    it = iter(groups)

    class _Fake:
        def assign(self):
            return next(it)

    return _Fake()


def main():
    tmp = tempfile.mkdtemp(prefix="qa_kpi_")
    db_path = Path(tmp) / "qa_test.db"
    store = Store(db_path)

    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: Settings(admin_api_token=ADMIN_TOKEN)
    # T1, T2 -> treatment / (control group has ZERO sessions/events at all: edge case)
    app.dependency_overrides[get_experiment_assigner] = lambda: force_group_sequence(
        [TREATMENT, TREATMENT]
    )

    client = TestClient(app)

    # === G-P2B1-5: 認証チェック(まずデータ投入前に) ===
    r_no_token = client.get("/api/admin/kpi")
    check("G-P2B1-5 no-token -> 401", r_no_token.status_code == 401, str(r_no_token.status_code))
    check(
        "G-P2B1-5 no-token error code",
        r_no_token.json().get("code") == "ADMIN_UNAUTHORIZED",
        str(r_no_token.json()),
    )

    r_wrong_token = client.get("/api/admin/kpi", headers={"X-Admin-Token": "totally-wrong"})
    check(
        "G-P2B1-5 wrong-token -> 401",
        r_wrong_token.status_code == 401,
        str(r_wrong_token.status_code),
    )

    r_right_token_empty = client.get("/api/admin/kpi", headers={"X-Admin-Token": ADMIN_TOKEN})
    check(
        "G-P2B1-5 right-token -> 200",
        r_right_token_empty.status_code == 200,
        str(r_right_token_empty.status_code),
    )

    # === データ投入: T1, T2 セッション作成（実APIの /api/session 経由）===
    # QR-ENTRANCE-001 は実データ（実在するdata/qr.json）に存在する前提（既存テストと同じ）。
    s1 = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
    s2 = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
    check("session T1 created 200", s1.status_code == 200, s1.text)
    check("session T2 created 200", s2.status_code == 200, s2.text)
    t1 = s1.json()
    t2 = s2.json()
    check("T1 group is treatment", t1["experiment_group"] == TREATMENT, t1["experiment_group"])
    check("T2 group is treatment", t2["experiment_group"] == TREATMENT, t2["experiment_group"])

    sid1 = t1["session_id"]
    sid2 = t2["session_id"]

    def post_event(sid, etype, payload=None):
        resp = client.post(
            "/api/events",
            json={"session_id": sid, "event_type": etype, "payload": payload or {}},
        )
        assert resp.status_code == 200, resp.text
        return resp

    # T1: qr_scan, related_view, related_tap, coordinate_view, chatbot_open
    post_event(sid1, "qr_scan")
    post_event(sid1, "related_view")
    post_event(sid1, "related_tap")
    post_event(sid1, "coordinate_view")
    post_event(sid1, "chatbot_open")

    # T1: route to P009 -> via_sub_passage should be True (real routing data, per test_route.py)
    # === G-P2B1-6: サブ通路通過率の結線を実route APIで確認 ===
    r_route1 = client.get(
        "/api/route",
        params={"from_qr": "QR-ENTRANCE-001", "to_product": "P009", "session_id": sid1},
    )
    check("G-P2B1-6 route to P009 200", r_route1.status_code == 200, r_route1.text)
    route1_body = r_route1.json()
    check(
        "G-P2B1-6 route to P009 has sub_passages waypoint",
        len(route1_body.get("sub_passages", [])) >= 1,
        str(route1_body.get("sub_passages")),
    )

    events_sid1 = store.list_events(session_id=sid1)
    route_view_events_sid1 = [e for e in events_sid1 if e["event_type"] == "route_view"]
    check(
        "G-P2B1-6 route_view payload has via_sub_passage=True for P009",
        len(route_view_events_sid1) == 1 and route_view_events_sid1[0]["payload"].get("via_sub_passage") is True,
        str(route_view_events_sid1),
    )

    # T2: qr_scan only, then route to P001 -> via_sub_passage should be False
    post_event(sid2, "qr_scan")
    r_route2 = client.get(
        "/api/route",
        params={"from_qr": "QR-ENTRANCE-001", "to_product": "P001", "session_id": sid2},
    )
    check("G-P2B1-6 route to P001 200", r_route2.status_code == 200, r_route2.text)
    events_sid2 = store.list_events(session_id=sid2)
    route_view_events_sid2 = [e for e in events_sid2 if e["event_type"] == "route_view"]
    check(
        "G-P2B1-6 route_view payload has via_sub_passage=False for P001",
        len(route_view_events_sid2) == 1 and route_view_events_sid2[0]["payload"].get("via_sub_passage") is False,
        str(route_view_events_sid2),
    )

    # === 手計算値（我々自身の計算） ===
    # treatment: session_count=2 (T1,T2 session_start via /api/session)
    #   scanned = qr_scan(T1,T2) union session_start(T1,T2) = {T1,T2} -> 2
    #   related_viewed = {T1} -> 1
    #   related_tapped = {T1} -> 1
    #   route_viewed = {T1,T2} -> 2
    #   coordinate_viewed = {T1} -> 1
    #   chatbot_opened = {T1} -> 1
    # rates:
    #   related_tap_rate = 1/1 = 1.0
    #   route_reach_rate = 2/2 = 1.0
    #   coordinate_view_rate = 1/2 = 0.5
    #   sub_passage_rate = 1/2 = 0.5 (T1 via_sub_passage True, T2 False; route_view_sessions=2, sub=1)
    # control: NO sessions/events at all -> all zero, rates 0.0 (denom-zero edge case)
    # diff = treatment - control (control is 0 for everything)
    expected_treatment_funnel = {
        "scanned": 2,
        "related_viewed": 1,
        "related_tapped": 1,
        "route_viewed": 2,
        "coordinate_viewed": 1,
        "chatbot_opened": 1,
    }
    expected_treatment_rates = {
        "related_tap_rate": 1.0,
        "route_reach_rate": 1.0,
        "coordinate_view_rate": 0.5,
        "sub_passage_rate": 0.5,
    }
    expected_control_funnel = {
        "scanned": 0,
        "related_viewed": 0,
        "related_tapped": 0,
        "route_viewed": 0,
        "coordinate_viewed": 0,
        "chatbot_opened": 0,
    }
    expected_control_rates = {
        "related_tap_rate": 0.0,
        "route_reach_rate": 0.0,
        "coordinate_view_rate": 0.0,
        "sub_passage_rate": 0.0,
    }
    expected_diff = {
        k: expected_treatment_rates[k] - expected_control_rates[k]
        for k in expected_treatment_rates
    }

    # === G-P2B1-7: POS突合スロット(値あり) をこちらで用意して override ===
    custom_pos = {
        TREATMENT: {
            "co_purchase_rate": 0.42,
            "items_per_purchase": 3.1,
            "spend_per_customer": 7777,
        },
        CONTROL: {
            "co_purchase_rate": 0.10,
            "items_per_purchase": 1.5,
            "spend_per_customer": 2000,
        },
    }
    app.dependency_overrides[get_pos_metrics] = lambda: custom_pos

    r_kpi = client.get("/api/admin/kpi", headers={"X-Admin-Token": ADMIN_TOKEN})
    check("kpi fetch 200", r_kpi.status_code == 200, r_kpi.text)
    body = r_kpi.json()

    print(json.dumps(body, indent=2, ensure_ascii=False))

    treatment_actual = body["groups"][TREATMENT]
    control_actual = body["groups"][CONTROL]

    check(
        "G-P2B1-4 treatment session_count == 2",
        treatment_actual["session_count"] == 2,
        str(treatment_actual["session_count"]),
    )
    check(
        "G-P2B1-4 treatment funnel matches hand-calc",
        treatment_actual["funnel"] == expected_treatment_funnel,
        f"actual={treatment_actual['funnel']} expected={expected_treatment_funnel}",
    )
    for k, v in expected_treatment_rates.items():
        check(
            f"G-P2B1-4 treatment rate[{k}] == {v}",
            abs(treatment_actual["rates"][k] - v) < 1e-9,
            f"actual={treatment_actual['rates'][k]}",
        )

    check(
        "G-P2B1-4 control session_count == 0 (edge: no events at all)",
        control_actual["session_count"] == 0,
        str(control_actual["session_count"]),
    )
    check(
        "G-P2B1-4 control funnel all-zero matches hand-calc",
        control_actual["funnel"] == expected_control_funnel,
        f"actual={control_actual['funnel']}",
    )
    for k, v in expected_control_rates.items():
        check(
            f"G-P2B1-4 control rate[{k}] == {v} (denom-zero edge)",
            abs(control_actual["rates"][k] - v) < 1e-9,
            f"actual={control_actual['rates'][k]}",
        )

    diff_actual = body["diff"]
    for k, v in expected_diff.items():
        check(
            f"G-P2B1-4 diff[{k}] == {v}",
            abs(diff_actual[k] - v) < 1e-9,
            f"actual={diff_actual[k]}",
        )

    # POS block check (G-P2B1-7, values present)
    pos_actual = body["pos_metrics"]
    check("G-P2B1-7 pos_metrics present (not None)", pos_actual is not None, str(pos_actual))
    if pos_actual is not None:
        check(
            "G-P2B1-7 pos treatment co_purchase_rate == 0.42",
            abs(pos_actual["groups"][TREATMENT]["co_purchase_rate"] - 0.42) < 1e-9,
        )
        check(
            "G-P2B1-7 pos control co_purchase_rate == 0.10",
            abs(pos_actual["groups"][CONTROL]["co_purchase_rate"] - 0.10) < 1e-9,
        )
        expected_pos_diff = {
            "co_purchase_rate": 0.42 - 0.10,
            "items_per_purchase": 3.1 - 1.5,
            "spend_per_customer": 7777 - 2000,
        }
        for k, v in expected_pos_diff.items():
            check(
                f"G-P2B1-7 pos diff[{k}] == {v}",
                abs(pos_actual["diff"][k] - v) < 1e-6,
                f"actual={pos_actual['diff'][k]}",
            )

    # === G-P2B1-7: POS突合スロット(値なし=None) ===
    app.dependency_overrides[get_pos_metrics] = lambda: None
    r_kpi_none = client.get("/api/admin/kpi", headers={"X-Admin-Token": ADMIN_TOKEN})
    check(
        "G-P2B1-7 pos_metrics None when dependency returns None",
        r_kpi_none.json()["pos_metrics"] is None,
        str(r_kpi_none.json()["pos_metrics"]),
    )

    # === G-P2B1-7: デフォルト(実データ data/pos_metrics.json)を上書きせず確認 ===
    app.dependency_overrides.pop(get_pos_metrics, None)
    r_kpi_default = client.get("/api/admin/kpi", headers={"X-Admin-Token": ADMIN_TOKEN})
    default_pos = r_kpi_default.json()["pos_metrics"]
    check(
        "G-P2B1-7 default (data/pos_metrics.json) pos_metrics is present",
        default_pos is not None,
        str(default_pos),
    )
    # Cross-check against the actual file on disk directly (independent read).
    pos_file = BACKEND_DIR.parent / "data" / "pos_metrics.json"
    check("G-P2B1-7 data/pos_metrics.json exists", pos_file.exists(), str(pos_file))
    if pos_file.exists():
        raw = json.loads(pos_file.read_text(encoding="utf-8"))
        print("raw pos_metrics.json:", raw)
        if default_pos is not None and raw:
            for g in (TREATMENT, CONTROL):
                for k in ("co_purchase_rate", "items_per_purchase", "spend_per_customer"):
                    file_v = raw.get(g, {}).get(k)
                    api_v = default_pos["groups"][g][k]
                    check(
                        f"G-P2B1-7 default pos [{g}][{k}] api matches file",
                        (file_v is None and api_v is None)
                        or (file_v is not None and api_v is not None and abs(file_v - api_v) < 1e-9),
                        f"file={file_v} api={api_v}",
                    )

    app.dependency_overrides.clear()

    print("\n=== SUMMARY ===")
    print(f"PASS: {len(results['pass'])}")
    print(f"FAIL: {len(results['fail'])}")
    if results["fail"]:
        print("FAILURES:")
        for f in results["fail"]:
            print(" -", f)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
