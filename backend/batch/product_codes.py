"""商品番号（`LL-MM-SS-NNN`）採番バッチ（新機能: 商品番号による直接遷移）。

QRを読み取れない来店客が、QR下部に併記された商品番号を入力すると、その商品のQRを
スキャンしたのと等価に直接進めるようにする（要件4.1 カメラ非対応フォールバックの拡張。
9章アクセシビリティ）。本バッチは `data/products.json` の各商品に商品番号
（`product_code`）を決定的に付与し、あわせて `data/qr_codes.json` の商品QR
（`type == "product"`）エントリにも同じ `product_code` を付与する（「QRと併記」を表現）。

## コード体系（確定仕様）
`LL-MM-SS-NNN`（合計9桁・階層式。表示はハイフン区切り、入力はハイフン有無どちらも許容
— `repositories.ProductRepository` 側で数字9桁に正規化して突合する）。

    LL  = 大分類コード（2桁, 01〜）。全商品に現れる大分類を**名称ソート**して安定採番。
    MM  = 中分類コード（2桁, 01〜）。その大分類配下に現れる中分類を名称ソートして安定採番。
    SS  = 小分類コード（2桁, 01〜）。その中分類配下に現れる小分類を名称ソートして安定採番。
    NNN = 個別番号（3桁, 001〜）。その小分類配下の商品を `product_id` 昇順
          （ソースデータで既に一意・安定なキー）で安定採番。

前提・注記（曖昧仕様の採用理由）: 仕様は「LL=大分類コード（名称ソートで安定採番）」を
明示するが、MM/SSの採番基準までは明示していない。LLと同じ「名称ソートによる決定的採番」を
階層全体で一貫して適用するのが最も自然かつ再現可能な解釈のため、MM/SSにも名称ソートを
採用する。NNN（個別番号）は「商品を安定順で」とのみ指定されているため、ソースJSON内で
既に一意なキーである `product_id` の昇順を「安定順」として採用する。

フルコード（9桁）は階層プレフィックス（LL-MM-SS）＋その配下でのみ振られる連番（NNN）の
組み合わせのため、構築時点で自動的に**全商品ユニーク**になる（同名の小分類が異なる
大分類・中分類に存在しても、上位桁が異なるため衝突しない）。

## 責務分離
- `assign_codes(products) -> products` … 純粋関数。I/Oに触れず、テスト容易性を担保する。
- `attach_codes_to_qr_codes(qr_codes, products_with_codes) -> qr_codes` … 純粋関数。
- `load_products()` / `write_products()` / `load_qr_codes()` / `write_qr_codes()` … I/O。
- `run()` … 上記を束ねるオーケストレーション（CLIからも呼ばれる）。

## CLI
    cd backend
    .venv\\Scripts\\python.exe -m batch.product_codes
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from dataio import DEFAULT_DATA_DIR, load_json_list

PRODUCTS_FILENAME = "products.json"
QR_CODES_FILENAME = "qr_codes.json"

LARGE_DIGITS = 2
MID_DIGITS = 2
SMALL_DIGITS = 2
SEQ_DIGITS = 3


def assign_codes(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """商品リストに `product_code`（`"LL-MM-SS-NNN"`）を決定的に付与する（純粋関数）。

    入力の並び順・既存キーは変更せず、`product_code` のみ追加/上書きした新しい
    辞書のリストを返す（同一入力から常に同一出力＝再現性を担保）。

    Raises:
        KeyError: 商品が `cat_large`/`cat_mid`/`cat_small`/`product_id` を欠く場合。
    """
    # 1) 大分類コード: 全商品に現れる大分類名を名称ソートして 01〜 を割り当てる。
    large_names = sorted({p["cat_large"] for p in products})
    large_codes = {name: str(i + 1).zfill(LARGE_DIGITS) for i, name in enumerate(large_names)}

    # 2) 中分類コード: 大分類ごとに、その配下の中分類名を名称ソートして 01〜 を割り当てる。
    mid_codes: dict[tuple[str, str], str] = {}
    for large_name in large_names:
        mid_names = sorted({p["cat_mid"] for p in products if p["cat_large"] == large_name})
        for i, mid_name in enumerate(mid_names):
            mid_codes[(large_name, mid_name)] = str(i + 1).zfill(MID_DIGITS)

    # 3) 小分類コード: 中分類ごとに、その配下の小分類名を名称ソートして 01〜 を割り当てる。
    small_codes: dict[tuple[str, str, str], str] = {}
    for large_name, mid_name in sorted(mid_codes.keys()):
        small_names = sorted(
            {
                p["cat_small"]
                for p in products
                if p["cat_large"] == large_name and p["cat_mid"] == mid_name
            }
        )
        for i, small_name in enumerate(small_names):
            small_codes[(large_name, mid_name, small_name)] = str(i + 1).zfill(SMALL_DIGITS)

    # 4) 個別番号: 小分類ごとに、その配下の商品を product_id 昇順で 001〜 を割り当てる。
    seq_codes: dict[str, str] = {}
    for large_name, mid_name, small_name in sorted(small_codes.keys()):
        members = sorted(
            (
                p
                for p in products
                if p["cat_large"] == large_name
                and p["cat_mid"] == mid_name
                and p["cat_small"] == small_name
            ),
            key=lambda p: p["product_id"],
        )
        for i, product in enumerate(members):
            seq_codes[product["product_id"]] = str(i + 1).zfill(SEQ_DIGITS)

    result: list[dict[str, Any]] = []
    for product in products:
        large_code = large_codes[product["cat_large"]]
        mid_code = mid_codes[(product["cat_large"], product["cat_mid"])]
        small_code = small_codes[
            (product["cat_large"], product["cat_mid"], product["cat_small"])
        ]
        seq_code = seq_codes[product["product_id"]]
        code = f"{large_code}-{mid_code}-{small_code}-{seq_code}"

        updated = dict(product)
        updated["product_code"] = code
        result.append(updated)

    return result


def attach_codes_to_qr_codes(
    qr_codes: list[dict[str, Any]], products_with_codes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """QRマスタの商品QR（`type == "product"`）エントリに `product_code` を併記する（純粋関数）。

    「QRと併記」（=QRの下に商品番号が表示されている状態）を表現するため、対応する
    `product_id` の `product_code` をコピーする。入口QR等、`product_id` を持たない/
    対応する商品が見つからないエントリは変更しない。
    """
    code_by_product_id = {
        p["product_id"]: p["product_code"] for p in products_with_codes if "product_code" in p
    }

    result: list[dict[str, Any]] = []
    for qr in qr_codes:
        updated = dict(qr)
        product_id = qr.get("product_id")
        if qr.get("type") == "product" and product_id in code_by_product_id:
            updated["product_code"] = code_by_product_id[product_id]
        result.append(updated)
    return result


def load_products(data_dir: Optional[Union[str, Path]] = None) -> list[dict[str, Any]]:
    return load_json_list(PRODUCTS_FILENAME, data_dir=data_dir)


def load_qr_codes(data_dir: Optional[Union[str, Path]] = None) -> list[dict[str, Any]]:
    return load_json_list(QR_CODES_FILENAME, data_dir=data_dir)


def write_products(
    products: list[dict[str, Any]], data_dir: Optional[Union[str, Path]] = None
) -> Path:
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    path = base / PRODUCTS_FILENAME
    path.write_text(json.dumps(products, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_qr_codes(
    qr_codes: list[dict[str, Any]], data_dir: Optional[Union[str, Path]] = None
) -> Path:
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    path = base / QR_CODES_FILENAME
    path.write_text(json.dumps(qr_codes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run(data_dir: Optional[Union[str, Path]] = None) -> dict[str, int]:
    """バッチ本体: 読み込み→採番→書き出しを行い、件数サマリを返す。"""
    products = load_products(data_dir=data_dir)
    updated_products = assign_codes(products)
    write_products(updated_products, data_dir=data_dir)

    qr_codes = load_qr_codes(data_dir=data_dir)
    updated_qr_codes = attach_codes_to_qr_codes(qr_codes, updated_products)
    write_qr_codes(updated_qr_codes, data_dir=data_dir)

    product_qr_with_code = sum(
        1
        for qr in updated_qr_codes
        if qr.get("type") == "product" and "product_code" in qr
    )
    return {
        "products": len(updated_products),
        "product_qr_codes": product_qr_with_code,
    }


def main() -> None:
    summary = run()
    print(
        f"products.json に商品番号（product_code）を付与しました: {summary['products']} 件"
        f"（うちQRマスタ(qr_codes.json)に product_code を併記: {summary['product_qr_codes']} 件）"
    )


if __name__ == "__main__":
    main()
