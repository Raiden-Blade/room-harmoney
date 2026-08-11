"""`GET /api/product-code/{code}`（新機能: 商品番号による直接遷移）。

QRを読み取れない来店客が、QRの下に併記された商品番号（`LL-MM-SS-NNN`。
`backend/batch/product_codes.py` で採番）を入力すると、その商品のQRをスキャンしたのと
**等価**に直接進めるようにする（要件4.1 カメラ非対応フォールバックの拡張・9章
アクセシビリティ）。本エンドポイントは商品番号→`(product_id, qr_id, position)` を
解決するだけで、以降のセッション開始（`POST /api/session`）・イベント記録はフロントが
既存のQR解決フロー（`qr_id` を渡す）にそのまま合流させることで、「商品QRをスキャンした
のと等価」を担保する（実装を分岐させない）。

入力は数字10桁・ハイフン有無どちらも許容（`ProductRepository.get_by_code` 側で正規化して
突合する）。未知のコードは404で明確な code/message を返す（19章 エラーハンドリング）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_product_repo, get_qr_repo
from ..errors import ApiError
from ..repositories import ProductRepository, QrRepository

router = APIRouter(tags=["product-code"])


@router.get("/api/product-code/{code}")
def resolve_product_code(
    code: str,
    product_repo: ProductRepository = Depends(get_product_repo),
    qr_repo: QrRepository = Depends(get_qr_repo),
) -> dict:
    product = product_repo.get_by_code(code)
    if product is None:
        raise ApiError(
            status_code=404,
            code="PRODUCT_CODE_NOT_FOUND",
            message=f"商品番号 {code} に該当する商品が見つかりません。番号をご確認ください。",
        )

    qr = qr_repo.get_by_product_id(product["product_id"])
    if qr is None:
        # サンプル/実データの参照整合性が崩れている場合のフォールバック
        # （通常は products.json/qr_codes.json とも `batch.product_codes` で同時生成されるため発生しない）。
        raise ApiError(
            status_code=404,
            code="PRODUCT_CODE_NOT_FOUND",
            message=f"商品番号 {code} に対応するQRが見つかりません。",
        )

    return {
        "product_id": product["product_id"],
        "qr_id": qr["qr_id"],
        "position": {"floor": qr["floor"], "x": qr["x"], "y": qr["y"]},
        "product_code": product.get("product_code"),
    }
