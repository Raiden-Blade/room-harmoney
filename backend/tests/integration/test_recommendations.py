"""`GET /api/recommendations`（17章）の結合テスト。B1 HybridRecommender 結線の確認と
来店ロック（AC-5）・計測ログ（AC-4/10章）を検証する。
"""
from __future__ import annotations


def test_recommendations_without_session_id_returns_409(client):
    """AC-5: session_id が無い状態での recommendations は来店ロックで 409。"""
    response = client.get("/api/recommendations", params={"product_id": "P001"})

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "VISIT_LOCK_REQUIRED"
    assert "QR" in body["message"]


def test_recommendations_with_bogus_session_id_returns_409(client):
    response = client.get(
        "/api/recommendations",
        params={"product_id": "P001", "session_id": "not-a-real-session"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "VISIT_LOCK_REQUIRED"


def test_recommendations_related_are_sorted_by_lift_descending(client, active_session):
    """B1結線の確認: P027（食器）の related は
    キッチン雑貨(lift1.3) → 収納ボックス(lift1.2) → カーテン(lift1.0) の順（リフト降順）。
    """
    response = client.get(
        "/api/recommendations",
        params={"product_id": "P027", "session_id": active_session["session_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    related = body["related"]

    assert [item["cat_mid"] for item in related] == [
        "キッチン雑貨",
        "キッチン雑貨",
        "キッチン雑貨",
        "収納ボックス",
        "収納ボックス",
        "収納ボックス",
        "カーテン",
        "カーテン",
    ]
    lifts = [item["lift"] for item in related]
    assert lifts == sorted(lifts, reverse=True)
    assert lifts[:3] == [1.3, 1.3, 1.3]
    assert lifts[3:6] == [1.2, 1.2, 1.2]
    assert lifts[6:] == [1.0, 1.0]


def test_recommendations_surface_high_lift_low_corate_flag(client, active_session):
    """P020（ダイニングテーブル）は「リフト高×併売率低」ペア（ラグ・カーペット）を含む。"""
    response = client.get(
        "/api/recommendations",
        params={"product_id": "P020", "session_id": active_session["session_id"]},
    )

    assert response.status_code == 200
    related = response.json()["related"]
    assert len(related) == 2
    assert all(item["cat_mid"] == "ラグ・カーペット" for item in related)
    assert all(item["high_lift_low_corate"] is True for item in related)
    assert all(item["lift"] == 2.8 for item in related)


def test_recommendations_includes_coordinates_containing_origin_product(client, active_session):
    """スキャン商品を含むコーディネートが1件以上返る（AC-2 の下地）。"""
    response = client.get(
        "/api/recommendations",
        params={"product_id": "P001", "session_id": active_session["session_id"]},
    )

    assert response.status_code == 200
    coordinates = response.json()["coordinates"]
    assert len(coordinates) >= 1
    assert any(c["coordinate_id"] == "C001" for c in coordinates)
    assert all("P001" in c["product_ids"] for c in coordinates)


def test_recommendations_unknown_product_with_valid_session_returns_404(client, active_session):
    response = client.get(
        "/api/recommendations",
        params={"product_id": "DOES-NOT-EXIST", "session_id": active_session["session_id"]},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"


def test_recommendations_related_default_limit_is_12(client, active_session):
    """段階B2: limit 未指定時は既定12件以内に切られる（P027は8件なので全件そのまま返る）。"""
    response = client.get(
        "/api/recommendations",
        params={"product_id": "P027", "session_id": active_session["session_id"]},
    )

    assert response.status_code == 200
    related = response.json()["related"]
    assert len(related) <= 12
    assert len(related) == 8  # P027（食器）の related は8件（既存テストと同じ前提）


def test_recommendations_limit_query_caps_related_count(client, active_session):
    """段階B2: limit を指定すると related が上位 limit 件（スコア降順）に切られる。"""
    response = client.get(
        "/api/recommendations",
        params={
            "product_id": "P027",
            "session_id": active_session["session_id"],
            "limit": 3,
        },
    )

    assert response.status_code == 200
    related = response.json()["related"]
    assert len(related) == 3
    # リフト降順の先頭3件（キッチン雑貨×3）のみが残ること。
    assert [item["cat_mid"] for item in related] == ["キッチン雑貨", "キッチン雑貨", "キッチン雑貨"]


def test_recommendations_limit_does_not_truncate_coordinates(client, active_session):
    """段階B2: limit は related のみに適用し、coordinates は対象外。"""
    response = client.get(
        "/api/recommendations",
        params={
            "product_id": "P001",
            "session_id": active_session["session_id"],
            "limit": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["related"]) <= 1
    assert len(body["coordinates"]) >= 1


def test_recommendations_records_related_view_event_with_experiment_group(
    client, active_session, store
):
    response = client.get(
        "/api/recommendations",
        params={"product_id": "P027", "session_id": active_session["session_id"]},
    )
    assert response.status_code == 200

    events = store.list_events(session_id=active_session["session_id"])
    related_view_events = [e for e in events if e["event_type"] == "related_view"]

    assert len(related_view_events) == 1
    event = related_view_events[0]
    assert event["experiment_group"] == active_session["experiment_group"]
    assert event["payload"]["product_id"] == "P027"
    assert "P033" in event["payload"]["related_product_ids"]
