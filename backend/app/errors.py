"""APIエラー統一フォーマット（17章末・19章 エラーハンドリング）。

不正な `qr_id`・存在しない `product_id`/`coordinate_id`・範囲外floor・経路なし・
来店ロックのいずれも、`{"code": ..., "message": ...}` という明確な本文とHTTPステータス
コードで返す。FastAPI標準の `{"detail": ...}` 形式ではなく、フロントが機械的に
`code` で分岐できるようトップレベルに `code`/`message` を出す。
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    """`code`（機械可読なエラー種別）と `message`（人が読める案内文）を持つHTTP例外。"""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message})
        self.code = code
        self.message = message


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"code": exc.code, "message": exc.message}
        )
