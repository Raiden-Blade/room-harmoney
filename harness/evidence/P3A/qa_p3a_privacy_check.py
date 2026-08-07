"""QA独立検算スクリプト（G-P3A-6 プライバシー確認, G-P3A-7 来店ロック無回帰）。
TestClientで隔離DB(実ファイル)に対して /api/recommendations?member_id=... を叩いた後、
Storeクラスを経由せず sqlite3 で直接DBファイル全体（sessions/events 全カラム）を
ダンプし、"M004" という文字列が一切出現しないことを確認する。
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(r"C:\Users\haseg\OneDrive\Documents\ニトリ制作物\room-harmony")
BACKEND_DIR = REPO / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.dependencies import get_settings, get_store  # noqa: E402
from app.main import app  # noqa: E402
from app.store import Store  # noqa: E402

results = {"pass": [], "fail": []}


def check(name, cond, detail=""):
    if cond:
        results["pass"].append(name)
        print(f"[PASS] {name} {detail}")
    else:
        results["fail"].append(name + " " + detail)
        print(f"[FAIL] {name} {detail}")


def main():
    tmp = tempfile.mkdtemp(prefix="qa_p3a_privacy_")
    db_path = Path(tmp) / "qa_p3a.db"
    store = Store(db_path)

    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: Settings(admin_api_token="qa-p3a-token")

    client = TestClient(app)

    # === G-P3A-7: member_id を付けても、有効セッション無しなら従来どおり409 ===
    r_no_session = client.get(
        "/api/recommendations", params={"product_id": "P027", "member_id": "M004"}
    )
    check(
        "G-P3A-7 no active session + member_id -> 409",
        r_no_session.status_code == 409,
        f"actual status={r_no_session.status_code} body={r_no_session.text}",
    )
    check(
        "G-P3A-7 error code == VISIT_LOCK_REQUIRED",
        r_no_session.json().get("code") == "VISIT_LOCK_REQUIRED",
        str(r_no_session.json()),
    )

    # bogus session_id も同様に409であることを確認
    r_bogus_session = client.get(
        "/api/recommendations",
        params={"product_id": "P027", "member_id": "M004", "session_id": "does-not-exist"},
    )
    check(
        "G-P3A-7 bogus session_id + member_id -> 409",
        r_bogus_session.status_code == 409,
        f"actual status={r_bogus_session.status_code}",
    )

    # === 有効セッションを作成 ===
    s = client.post("/api/session", json={"qr_id": "QR-ENTRANCE-001"})
    check("session created 200", s.status_code == 200, s.text)
    sid = s.json()["session_id"]

    # === G-P3A-6: member_id=M004 付きで叩く ===
    r = client.get(
        "/api/recommendations",
        params={"product_id": "P027", "session_id": sid, "member_id": "M004"},
    )
    check("recommendations with member_id 200", r.status_code == 200, r.text)
    body = r.json()
    check("response personalized == True", body.get("personalized") is True, str(body.get("personalized")))
    # レスポンスJSON全体に "M004" が出現しないことも確認(レスポンスにmember_idを含めない設計の確認)
    resp_serialized = json.dumps(body, ensure_ascii=False)
    check(
        "GET /api/recommendations レスポンスJSONに'M004'文字列が出現しない",
        "M004" not in resp_serialized,
        "" if "M004" not in resp_serialized else "response body contained M004!",
    )

    app.dependency_overrides.clear()

    # === DB を Store 経由ではなく sqlite3 で直接、全テーブル・全カラムをダンプして検査 ===
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print("DB tables:", tables)

    full_dump_text = ""
    for t in tables:
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        for row in rows:
            d = dict(row)
            full_dump_text += json.dumps(d, ensure_ascii=False, default=str)
            print(f"[{t}]", d)

    check(
        "G-P3A-6 DB全体(sessions+events, 全カラム, sqlite3直読み)に'M004'という文字列が一切出現しない",
        "M004" not in full_dump_text,
        "" if "M004" not in full_dump_text else "FOUND 'M004' IN RAW DB DUMP!",
    )

    all_events = conn.execute("SELECT * FROM events").fetchall()
    check(
        "events table has exactly 2 rows (session_start + related_view)",
        len(all_events) == 2,
        str(len(all_events)),
    )
    events = [dict(r) for r in all_events if dict(r)["event_type"] == "related_view"]
    check("exactly 1 related_view event", len(events) == 1, str(len(events)))
    if events:
        ev = events[0]
        payload = json.loads(ev["payload"])
        print("event payload (raw column):", payload)
        check("event_type == related_view", ev["event_type"] == "related_view", ev["event_type"])
        check("payload has personalized=True", payload.get("personalized") is True, str(payload))
        check("payload has no 'member_id' key", "member_id" not in payload, str(list(payload.keys())))
        check(
            "payload keys are exactly the expected set (no extra member fields)",
            set(payload.keys()) == {"product_id", "related_product_ids", "coordinate_ids", "personalized"},
            str(set(payload.keys())),
        )

    conn.close()

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
