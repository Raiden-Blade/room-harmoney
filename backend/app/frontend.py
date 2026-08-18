"""構築済みReactフロントをFastAPIと同一プロセスで配信する。

開発時は従来どおりViteを使う。配布版だけ ``ROOM_HARMONY_SERVE_FRONTEND=1`` と
``FRONTEND_DIST_DIR`` を設定し、このモジュールを有効にする。APIの未知パスをReactの
``index.html`` へ誤フォールバックさせないこと、クライアント側ルート（``/s/...`` 等）は
リロードしても同じ画面へ戻れることを両立させる。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles


class SpaStaticFiles(StaticFiles):
    """静的ファイルを配信し、画面ルートだけSPAのindexへフォールバックする。"""

    def __init__(self, directory: Path):
        # StaticFilesのhtmlモードは未知のパスにindexを返すため、未知の /api/* まで
        # 200になる余地がある。ここでは無効化し、下の条件付きフォールバックだけを使う。
        super().__init__(directory=str(directory), html=False, check_dir=True)
        self._index_path = directory / "index.html"

    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not self._is_spa_navigation(path, scope):
                raise
            return self._index_response()

        if response.status_code == 404 and self._is_spa_navigation(path, scope):
            return self._index_response()
        return response

    def _is_spa_navigation(self, path: str, scope: dict[str, Any]) -> bool:
        if scope.get("method") not in {"GET", "HEAD"}:
            return False
        # Mount("/")配下ではStaticFilesへ渡るpathが先頭セグメントを失うStarlette版が
        # あるため、API判定にはASGI scopeの元リクエストパスを優先する。
        normalized = str(scope.get("path") or path).lstrip("/")
        if normalized == "api" or normalized.startswith("api/"):
            return False
        # 拡張子付きの未知リソース（例えば存在しない.js/.png）は404のまま返す。
        return not Path(normalized).suffix

    def _index_response(self) -> FileResponse:
        return FileResponse(
            self._index_path,
            headers={"Cache-Control": "no-cache"},
        )


def mount_bundled_frontend(app: FastAPI) -> None:
    """配布モードでだけ、全APIルートの後ろに構築済みフロントをマウントする。"""
    if os.environ.get("ROOM_HARMONY_SERVE_FRONTEND") != "1":
        return

    raw_dir = os.environ.get("FRONTEND_DIST_DIR")
    if not raw_dir:
        raise RuntimeError("FRONTEND_DIST_DIR is required in bundled frontend mode")

    frontend_dir = Path(raw_dir).expanduser().resolve()
    index_path = frontend_dir / "index.html"
    if not index_path.is_file():
        raise RuntimeError(f"Bundled frontend index.html was not found: {index_path}")

    # このmountは必ずAPIルーターと /health の登録後に呼ぶ。Starletteは登録順で評価する。
    app.mount("/", SpaStaticFiles(frontend_dir), name="bundled-frontend")
