"""QA独立検証スクリプト（フェーズ3-B / Wi-Fi・ジオフェンス来店判定）。

実装エージェントのテストコード(tests/unit/test_visit.py, tests/integration/test_visit_verification.py)
とは別に、QAが自作したスクリプトで G-P3B-4〜7 を独立に確認する。
- G-P3B-4: 既定モード(qr)の無回帰。位置シグナル無しで recommendations/route が従来どおり動作。
           来店ロック無し(session_id無し)では409になること。
- G-P3B-5: qr+geofence モード。店内→200、店外→409、位置欠如→409、境界(150m)付近1点。
- G-P3B-6: qr+wifi モード。許可SSID→200、非許可/欠如→409。
- G-P3B-7: プライバシー。geofence/wifiモードで位置・SSIDを送ったセッションで
           events テーブルに緯度経度・SSID文字列が一切保存されないことをDB直読みで確認。
           sessions テーブルには保持されること。

実行: backend\\.venv\\Scripts\\python.exe qa_p3b_independent_check.py
"""
from __future__ import annotations

import math
import random
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.dependencies import get_experiment_assigner, get_store  # noqa: E402
from app.experiment import ExperimentAssigner  # noqa: E402
from app.main import app  # noqa: E402
from app.store import Store  # noqa: E402

STORE_LAT = 35.6203
STORE_LNG = 139.6883
RADIUS_M = 150.0
OUTSIDE_LAT = 35.0
OUTSIDE_LNG = 135.0
ALLOWED_SSID = "Nitori-Free-Wifi"
DISALLOWED_SSID = "Some-Random-Wifi"

EARTH_R = 6371000.0


def lat_offset_for_distance(distance_m: float) -> float:
    return math.degrees(distance_m / EARTH_R)


results = []


def record(gate: str, name: str, ok: bool, detail: str = ""):
    results.append((gate, name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {gate} - {name} {('- ' + detail) if detail else ''}")


def make_client(db_path: Path, mode: str = "qr") -> TestClient:
    store = Store(db_path)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_experiment_assigner] = lambda: ExperimentAssigner(
        rng=random.Random(999)
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        visit_verification_mode=mode
    )
    client = TestClient(app)
    return client, store


def reset_overrides():
    app.dependency_overrides.clear()


def db_dump(db_path: Path, label: str):
    out_dir = Path(__file__).resolve().parent
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    lines = [f"# DB dump: {label} ({db_path})\n"]
    lines.append("## sessions\n")
    for row in conn.execute("SELECT * FROM sessions"):
        lines.append(str(dict(row)) + "\n")
    lines.append("\n## events\n")
    for row in conn.execute("SELECT * FROM events"):
        lines.append(str(dict(row)) + "\n")
    conn.close()
    (out_dir / f"db_dump_{label}.txt").write_text("".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# G-P3B-4: 既定モード(qr) 無回帰
# ---------------------------------------------------------------------------
work_dir = Path(__file__).resolve().parent
db4 = work_dir / "qa_check_g4.db"
if db4.exists():
    db4.unlink()
client, store = make_client(db4, mode="qr")

# 位置シグナル無しでセッション作成
resp = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
record("G-P3B-4", "default qr session create (no location) -> 200", resp.status_code == 200, str(resp.status_code))
session_id = resp.json().get("session_id")

rec = client.get("/api/recommendations", params={"product_id": "P001", "session_id": session_id})
record("G-P3B-4", "recommendations with default qr session -> 200", rec.status_code == 200, str(rec.status_code))

route = client.get("/api/route", params={"from_qr": "QR-ENTRANCE-001", "to_product": "P001", "session_id": session_id})
record("G-P3B-4", "route with default qr session -> 200", route.status_code == 200, str(route.status_code))

# 来店ロック無し(session_id無し)は 409
rec_nolock = client.get("/api/recommendations", params={"product_id": "P001"})
record(
    "G-P3B-4",
    "recommendations without session_id -> 409 VISIT_LOCK_REQUIRED",
    rec_nolock.status_code == 409 and rec_nolock.json().get("code") == "VISIT_LOCK_REQUIRED",
    f"status={rec_nolock.status_code} body={rec_nolock.text}",
)

route_nolock = client.get("/api/route", params={"from_qr": "QR-ENTRANCE-001", "to_product": "P001"})
record(
    "G-P3B-4",
    "route without session_id -> 409 VISIT_LOCK_REQUIRED",
    route_nolock.status_code == 409 and route_nolock.json().get("code") == "VISIT_LOCK_REQUIRED",
    f"status={route_nolock.status_code} body={route_nolock.text}",
)

db_dump(db4, "g4_default_qr")
reset_overrides()
client.close()

# ---------------------------------------------------------------------------
# G-P3B-5: geofence 分岐
# ---------------------------------------------------------------------------
db5 = work_dir / "qa_check_g5.db"
if db5.exists():
    db5.unlink()
client, store = make_client(db5, mode="qr+geofence")

resp_in = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001", "location": {"lat": STORE_LAT, "lng": STORE_LNG}})
sid_in = resp_in.json().get("session_id")
rec_in = client.get("/api/recommendations", params={"product_id": "P001", "session_id": sid_in})
record("G-P3B-5", "inside store coords -> 200", rec_in.status_code == 200, str(rec_in.status_code))

resp_out = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001", "location": {"lat": OUTSIDE_LAT, "lng": OUTSIDE_LNG}})
sid_out = resp_out.json().get("session_id")
rec_out = client.get("/api/recommendations", params={"product_id": "P001", "session_id": sid_out})
record(
    "G-P3B-5",
    "outside store coords -> 409 VISIT_NOT_VERIFIED",
    rec_out.status_code == 409 and rec_out.json().get("code") == "VISIT_NOT_VERIFIED",
    f"status={rec_out.status_code} body={rec_out.text}",
)

resp_missing = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
sid_missing = resp_missing.json().get("session_id")
rec_missing = client.get("/api/recommendations", params={"product_id": "P001", "session_id": sid_missing})
record(
    "G-P3B-5",
    "missing location -> 409 VISIT_NOT_VERIFIED",
    rec_missing.status_code == 409 and rec_missing.json().get("code") == "VISIT_NOT_VERIFIED",
    f"status={rec_missing.status_code} body={rec_missing.text}",
)

# 境界付近: 半径ちょうど(150m)は合格、151mは不合格 (子午線方向オフセットで厳密計算)
delta_at = lat_offset_for_distance(RADIUS_M)
resp_boundary_ok = client.post(
    "/api/session",
    json={"qr_id": "QR-ENTRANCE-001", "location": {"lat": STORE_LAT + delta_at, "lng": STORE_LNG}},
)
sid_boundary_ok = resp_boundary_ok.json().get("session_id")
rec_boundary_ok = client.get("/api/recommendations", params={"product_id": "P001", "session_id": sid_boundary_ok})
record(
    "G-P3B-5",
    "boundary exactly at radius(150m) -> 200 (<=)",
    rec_boundary_ok.status_code == 200,
    str(rec_boundary_ok.status_code),
)

delta_over = lat_offset_for_distance(RADIUS_M + 1.0)
resp_boundary_ng = client.post(
    "/api/session",
    json={"qr_id": "QR-ENTRANCE-001", "location": {"lat": STORE_LAT + delta_over, "lng": STORE_LNG}},
)
sid_boundary_ng = resp_boundary_ng.json().get("session_id")
rec_boundary_ng = client.get("/api/recommendations", params={"product_id": "P001", "session_id": sid_boundary_ng})
record(
    "G-P3B-5",
    "boundary 1m over radius(151m) -> 409",
    rec_boundary_ng.status_code == 409,
    str(rec_boundary_ng.status_code),
)

db_dump(db5, "g5_geofence")
reset_overrides()
client.close()

# ---------------------------------------------------------------------------
# G-P3B-6: wifi 分岐
# ---------------------------------------------------------------------------
db6 = work_dir / "qa_check_g6.db"
if db6.exists():
    db6.unlink()
client, store = make_client(db6, mode="qr+wifi")

resp_allowed = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001", "wifi_ssid": ALLOWED_SSID})
sid_allowed = resp_allowed.json().get("session_id")
rec_allowed = client.get("/api/recommendations", params={"product_id": "P001", "session_id": sid_allowed})
record("G-P3B-6", "allowed SSID -> 200", rec_allowed.status_code == 200, str(rec_allowed.status_code))

resp_disallowed = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001", "wifi_ssid": DISALLOWED_SSID})
sid_disallowed = resp_disallowed.json().get("session_id")
rec_disallowed = client.get("/api/recommendations", params={"product_id": "P001", "session_id": sid_disallowed})
record(
    "G-P3B-6",
    "disallowed SSID -> 409 VISIT_NOT_VERIFIED",
    rec_disallowed.status_code == 409 and rec_disallowed.json().get("code") == "VISIT_NOT_VERIFIED",
    f"status={rec_disallowed.status_code} body={rec_disallowed.text}",
)

resp_nossid = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
sid_nossid = resp_nossid.json().get("session_id")
rec_nossid = client.get("/api/recommendations", params={"product_id": "P001", "session_id": sid_nossid})
record(
    "G-P3B-6",
    "missing SSID -> 409 VISIT_NOT_VERIFIED",
    rec_nossid.status_code == 409 and rec_nossid.json().get("code") == "VISIT_NOT_VERIFIED",
    f"status={rec_nossid.status_code} body={rec_nossid.text}",
)

db_dump(db6, "g6_wifi")
reset_overrides()
client.close()

# ---------------------------------------------------------------------------
# G-P3B-7: プライバシー確認 (events に位置/SSIDが一切保存されないこと)
# ---------------------------------------------------------------------------
db7 = work_dir / "qa_check_g7.db"
if db7.exists():
    db7.unlink()
client, store = make_client(db7, mode="qr+geofence+wifi")

resp = client.post(
    "/api/session",
    json={
        "qr_id": "QR-ENTRANCE-001",
        "location": {"lat": STORE_LAT, "lng": STORE_LNG},
        "wifi_ssid": ALLOWED_SSID,
    },
)
sid = resp.json().get("session_id")
client.get("/api/recommendations", params={"product_id": "P001", "session_id": sid})
client.get("/api/route", params={"from_qr": "QR-ENTRANCE-001", "to_product": "P001", "session_id": sid})
client.post("/api/events", json={"session_id": sid, "event_type": "qr_scanned", "payload": {"product_id": "P001"}})

db_dump(db7, "g7_privacy")

# 直接DBに接続してQA自身でクエリ(実装のstore.list_eventsは使わずsqlite3を直接叩く)
conn = sqlite3.connect(db7)
conn.row_factory = sqlite3.Row

sessions_rows = conn.execute("SELECT * FROM sessions").fetchall()
record(
    "G-P3B-7",
    "sessions table retains location_lat/lng/wifi_ssid for verification",
    len(sessions_rows) == 1
    and sessions_rows[0]["location_lat"] == STORE_LAT
    and sessions_rows[0]["location_lng"] == STORE_LNG
    and sessions_rows[0]["wifi_ssid"] == ALLOWED_SSID,
    str(dict(sessions_rows[0])) if sessions_rows else "no session row",
)

events_rows = conn.execute("SELECT * FROM events").fetchall()
forbidden_substrings = [str(STORE_LAT), str(STORE_LNG), ALLOWED_SSID, "location_lat", "location_lng", "wifi_ssid", '"lat"', '"lng"', '"ssid"']

leak_found = False
leak_detail = ""
column_names = events_rows[0].keys() if events_rows else []
record("G-P3B-7", "events rows exist for this session (sanity check, not empty)", len(events_rows) >= 1, str(len(events_rows)))
record(
    "G-P3B-7",
    "events table schema has no location_lat/location_lng/wifi_ssid column",
    not any(c in ("location_lat", "location_lng", "wifi_ssid") for c in column_names),
    str(list(column_names)),
)
for row in events_rows:
    full_row_str = str(dict(row))
    for needle in forbidden_substrings:
        if needle in full_row_str:
            leak_found = True
            leak_detail = f"event id={row['id']} type={row['event_type']} contains forbidden substring '{needle}': {full_row_str}"
            break
    if leak_found:
        break

record(
    "G-P3B-7",
    "no event row (full column dump incl. payload) contains lat/lng/ssid values or key names",
    not leak_found,
    leak_detail,
)
conn.close()
reset_overrides()
client.close()

# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
print("\n=== SUMMARY ===")
total = len(results)
passed = sum(1 for _, _, ok, _ in results if ok)
for gate, name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'} | {gate} | {name}")
print(f"\n{passed}/{total} checks passed")
if passed != total:
    sys.exit(1)
