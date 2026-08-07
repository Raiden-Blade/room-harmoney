"""`GET /api/recommendations?member_id=...`（フェーズ3-A / DECISIONS.md 改訂#5-A）の結合テスト。

観点:
  - member_id 無し: 従来どおり（`test_recommendations.py` のリフト順と完全一致）
  - member_id あり（アフィニティ会員）: 個人最適化で並びが変わる
  - member_id あり（未知/履歴空）: base と完全一致（後方互換）
  - プライバシー厳守（9章）: member_id が events テーブルに一切保存されない
  - 来店ロック（AC-5）等の既存の来店ロック挙動は維持される
"""
from __future__ import annotations


def test_recommendations_without_member_id_matches_base_order(client, active_session):
    """member_id 無しは従来どおり（test_recommendations.py と同じリフト降順）。"""
    response = client.get(
        "/api/recommendations",
        params={"product_id": "P027", "session_id": active_session["session_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["personalized"] is False
    assert [item["cat_mid"] for item in body["related"]] == [
        "キッチン雑貨",
        "キッチン雑貨",
        "キッチン雑貨",
        "収納ボックス",
        "収納ボックス",
        "収納ボックス",
        "カーテン",
        "カーテン",
    ]


def test_recommendations_with_affinity_member_reorders_related(client, active_session):
    """M004（サンプル会員: カーテン3回購入）で P027 の関連商品を見ると、
    カーテン中分類が親和度ブーストでキッチン雑貨より上位に来る（base順から変化）。
    """
    response = client.get(
        "/api/recommendations",
        params={
            "product_id": "P027",
            "session_id": active_session["session_id"],
            "member_id": "M004",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["personalized"] is True

    related = body["related"]
    assert [item["cat_mid"] for item in related] == [
        "カーテン",
        "カーテン",
        "キッチン雑貨",
        "キッチン雑貨",
        "キッチン雑貨",
        "収納ボックス",
        "収納ボックス",
        "収納ボックス",
    ]
    # lift 自体（データ由来の値）は変えない。並び用のブーストは score のみに反映。
    curtain_items = [item for item in related if item["cat_mid"] == "カーテン"]
    assert all(item["lift"] == 1.0 for item in curtain_items)
    assert [item["product"]["product_id"] for item in curtain_items] == ["P016", "P017"]


def test_recommendations_with_unknown_member_id_matches_base_order(client, active_session):
    """履歴に存在しない member_id は base と完全一致（後方互換）。"""
    base_response = client.get(
        "/api/recommendations",
        params={"product_id": "P027", "session_id": active_session["session_id"]},
    )
    unknown_member_response = client.get(
        "/api/recommendations",
        params={
            "product_id": "P027",
            "session_id": active_session["session_id"],
            "member_id": "NO-SUCH-MEMBER",
        },
    )

    assert unknown_member_response.status_code == 200
    assert unknown_member_response.json()["related"] == base_response.json()["related"]
    assert unknown_member_response.json()["personalized"] is True  # 会員IDは指定された


def test_recommendations_with_empty_history_member_matches_base_order(client, active_session):
    """サンプル会員 M003（購入履歴が空）は base と完全一致。"""
    base_response = client.get(
        "/api/recommendations",
        params={"product_id": "P027", "session_id": active_session["session_id"]},
    )
    empty_history_response = client.get(
        "/api/recommendations",
        params={
            "product_id": "P027",
            "session_id": active_session["session_id"],
            "member_id": "M003",
        },
    )

    assert empty_history_response.status_code == 200
    assert empty_history_response.json()["related"] == base_response.json()["related"]


def test_member_id_is_not_persisted_in_events(client, active_session, store):
    """9章プライバシー厳守: member_id は events（効果ログ）に一切保存されない。"""
    response = client.get(
        "/api/recommendations",
        params={
            "product_id": "P027",
            "session_id": active_session["session_id"],
            "member_id": "M004",
        },
    )
    assert response.status_code == 200

    events = store.list_events(session_id=active_session["session_id"])
    related_view_events = [e for e in events if e["event_type"] == "related_view"]
    assert len(related_view_events) == 1

    event = related_view_events[0]
    assert event["payload"]["personalized"] is True
    assert "member_id" not in event["payload"]

    # payload全体・イベント全体のどこにも "M004" という値が出現しないことを確認する
    # （member_id をキー名変更等で紛れ込ませていないかの網羅チェック）。
    import json

    serialized = json.dumps(event, ensure_ascii=False)
    assert "M004" not in serialized
    assert "member_id" not in event


def test_visit_lock_still_enforced_with_member_id_query(client):
    """AC-5: member_id を付けても、有効な来店セッションが無ければ来店ロックのまま409。"""
    response = client.get(
        "/api/recommendations",
        params={"product_id": "P027", "member_id": "M004"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "VISIT_LOCK_REQUIRED"
