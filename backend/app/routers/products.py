"""`GET /api/products/{product_id}`（17章）: 商品詳細。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_product_repo
from ..errors import ApiError
from ..repositories import ProductRepository

router = APIRouter(tags=["products"])


@router.get("/api/products/{product_id}")
def get_product(
    product_id: str, product_repo: ProductRepository = Depends(get_product_repo)
) -> dict:
    product = product_repo.get(product_id)
    if product is None:
        raise ApiError(
            status_code=404,
            code="PRODUCT_NOT_FOUND",
            message=f"product_id={product_id} は見つかりません。",
        )
    return product
