"""`backend/app/repositories.py` の `QrRepository` パターン解決フォールバックの単体テスト
（段階B2: 実商品データ9,180件への差し替えで qr_codes.json に商品QRを全件明示列挙しない
方針を採るための機能）。

重点観点:
  (1) 明示エントリが `qr_codes.json` に無くても、`QR-PRODUCT-<商品コード>` 形式なら
      `ProductRepository` 経由でその場で解決できる
  (2) 明示エントリがある場合は、それが優先される（後方互換。フィクスチャ/サンプルデータ）
  (3) `product_repo` 未設定（None）なら、従来どおりフォールバックせず None を返す
  (4) `QR-PRODUCT-` プレフィックスでない qr_id や、該当商品コードが存在しない場合は None
"""
from __future__ import annotations

from app.repositories import ProductRepository, QrRepository


def _product_repo() -> ProductRepository:
    return ProductRepository(
        [
            {
                "product_id": "R001",
                "product_code": "01-02-01-0001",
                "floor": 3,
                "x": 77,
                "y": 18,
                "name": "テスト商品",
            }
        ]
    )


def test_pattern_fallback_resolves_product_code_without_explicit_entry():
    """(1) 明示エントリが無い QR-PRODUCT-<商品コード> でも解決できる。"""
    qr_repo = QrRepository([], product_repo=_product_repo())

    result = qr_repo.get("QR-PRODUCT-01-02-01-0001")

    assert result is not None
    assert result["type"] == "product"
    assert result["product_id"] == "R001"
    assert result["floor"] == 3
    assert result["x"] == 77
    assert result["y"] == 18
    assert result["direct_url"] == "https://roomharmony.example.com/r/QR-PRODUCT-01-02-01-0001"
    assert result["product_code"] == "01-02-01-0001"


def test_pattern_fallback_accepts_digits_only_code():
    """(1) 商品コードのハイフン有無に依存せず解決できる（ProductRepository側で正規化）。"""
    qr_repo = QrRepository([], product_repo=_product_repo())

    result = qr_repo.get("QR-PRODUCT-0102010001")

    assert result is not None
    assert result["product_id"] == "R001"


def test_explicit_entry_takes_precedence_over_pattern_fallback():
    """(2) qr_codes.json に明示エントリがある場合はそちらが優先される（後方互換）。"""
    explicit_qr = {
        "qr_id": "QR-PRODUCT-01-02-01-0001",
        "type": "product",
        "product_id": "R001",
        "floor": 1,
        "x": 1,
        "y": 1,
        "direct_url": "https://roomharmony.example.com/r/QR-PRODUCT-01-02-01-0001",
    }
    qr_repo = QrRepository([explicit_qr], product_repo=_product_repo())

    result = qr_repo.get("QR-PRODUCT-01-02-01-0001")

    # フォールバックが生成する floor=3 ではなく、明示エントリの floor=1 が返る。
    assert result == explicit_qr


def test_fallback_disabled_when_product_repo_not_provided():
    """(3) product_repo 未設定なら、従来どおりフォールバックせず None（404相当）。"""
    qr_repo = QrRepository([])

    assert qr_repo.get("QR-PRODUCT-01-02-01-0001") is None


def test_fallback_returns_none_for_non_product_prefix():
    """(4) QR-PRODUCT- で始まらない qr_id はパターン解決の対象外。"""
    qr_repo = QrRepository([], product_repo=_product_repo())

    assert qr_repo.get("QR-ENTRANCE-999") is None


def test_fallback_returns_none_for_unknown_product_code():
    """(4) 商品コードが実在しない場合は None（404相当）。"""
    qr_repo = QrRepository([], product_repo=_product_repo())

    assert qr_repo.get("QR-PRODUCT-99-99-99-9999") is None
