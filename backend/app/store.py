"""セッション/イベントログの永続化層（6章・10章 / DESIGN.md sessions・events）。

SQLite（開発）を stdlib `sqlite3` で薄くラップする。責務分離のため、API層（routers）は
この `Store` を通じてのみ DB にアクセスする。

テスト容易性:
- コンストラクタは DB ファイルパスを直接受け取る（データ注入）。本番/開発は
  `Settings.database_path`（`.env` の `DATABASE_URL`）から解決したパスを使うが、
  結合テストでは `tmp_path` 配下の隔離ファイルを渡すことで本番/開発DBを汚さずに検証できる
  （FastAPI の `dependency_overrides` で `get_store` を差し替える）。
- 呼び出しの都度 SQLite 接続を開いて閉じる設計にしている。理由（コメント）:
  FastAPI の同期エンドポイントは Starlette によりスレッドプールで実行され得るため、
  単一のコネクションを使い回すと `sqlite3` のスレッド制約に抵触しうる。都度接続する
  ことで安全にする（引き換えに ":memory:" は接続ごとに空DBになるため使えない。
  そのためテストは in-memory ではなく `tmp_path` の実ファイルで隔離する）。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

_SESSIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    qr_id TEXT NOT NULL,
    floor INTEGER NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    store_id TEXT,
    experiment_group TEXT NOT NULL,
    created_at TEXT NOT NULL,
    location_lat REAL,
    location_lng REAL,
    wifi_ssid TEXT
)
"""

# フェーズ3-B（来店判定の高度化）で追加した任意カラム。既存のDBファイル（旧スキーマで
# 作成済み）に対しても `ALTER TABLE ... ADD COLUMN` で後方互換に拡張する
# （`CREATE TABLE IF NOT EXISTS` は既存テーブルのカラムを追加してくれないため）。
# いずれも判定用の一時的な位置シグナルであり、`events`（効果ログ）には保存しない
# （9章プライバシー「ログはセッション単位で匿名」）。
_SESSIONS_MIGRATION_COLUMNS = {
    "location_lat": "REAL",
    "location_lng": "REAL",
    "wifi_ssid": "TEXT",
}

_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    experiment_group TEXT,
    timestamp TEXT NOT NULL
)
"""


class Store:
    """sessions / events テーブルへの読み書きを担う薄いデータ層。"""

    def __init__(self, db_path: Union[str, Path]):
        self._db_path = str(db_path)
        parent = Path(self._db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_SESSIONS_SCHEMA)
            conn.execute(_EVENTS_SCHEMA)
            self._migrate_sessions_columns(conn)

    def _migrate_sessions_columns(self, conn: sqlite3.Connection) -> None:
        """旧スキーマの `sessions` テーブルに、フェーズ3-B追加カラムが無ければ足す。"""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
        for column, sql_type in _SESSIONS_MIGRATION_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {column} {sql_type}")

    # -- sessions ---------------------------------------------------------
    def create_session(
        self,
        *,
        session_id: str,
        qr_id: str,
        floor: int,
        x: float,
        y: float,
        store_id: Optional[str],
        experiment_group: str,
        location_lat: Optional[float] = None,
        location_lng: Optional[float] = None,
        wifi_ssid: Optional[str] = None,
    ) -> dict[str, Any]:
        """来店セッションを作成する。

        `location_lat`/`location_lng`/`wifi_ssid` はフェーズ3-B（来店判定の高度化）で
        追加した**任意**の来店判定シグナル。QR起点のみの既定モード(`qr`)では未指定でも
        従来どおり動作する（後方互換）。9章プライバシーのため、これらは `sessions`
        （判定用）にのみ保持し、`events`（効果ログ）には一切書き込まない。
        """
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions
                    (session_id, qr_id, floor, x, y, store_id, experiment_group, created_at,
                     location_lat, location_lng, wifi_ssid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    qr_id,
                    floor,
                    x,
                    y,
                    store_id,
                    experiment_group,
                    created_at,
                    location_lat,
                    location_lng,
                    wifi_ssid,
                ),
            )
        return {
            "session_id": session_id,
            "qr_id": qr_id,
            "floor": floor,
            "x": x,
            "y": y,
            "store_id": store_id,
            "experiment_group": experiment_group,
            "created_at": created_at,
            "location_lat": location_lat,
            "location_lng": location_lng,
            "wifi_ssid": wifi_ssid,
        }

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    # -- events -------------------------------------------------------------
    def insert_event(
        self,
        session_id: str,
        event_type: str,
        payload: Optional[dict[str, Any]],
        experiment_group: Optional[str],
    ) -> dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO events (session_id, event_type, payload, experiment_group, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, event_type, payload_json, experiment_group, timestamp),
            )
            event_id = cur.lastrowid
        return {
            "event_id": event_id,
            "session_id": session_id,
            "event_type": event_type,
            "payload": payload or {},
            "experiment_group": experiment_group,
            "timestamp": timestamp,
        }

    def list_events(self, session_id: Optional[str] = None) -> list[dict[str, Any]]:
        """イベントを時系列で返す（結合テストからのDBアサート用）。"""
        with self._connect() as conn:
            if session_id is not None:
                rows = conn.execute(
                    "SELECT * FROM events WHERE session_id = ? ORDER BY id", (session_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM events ORDER BY id").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            result.append(item)
        return result
