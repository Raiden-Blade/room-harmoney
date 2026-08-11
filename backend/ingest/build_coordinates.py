"""暫定コーディネート生成バッチ（段階B2: 実商品データへの差し替え）。

`data/coordinates.json` はもともと手入力のキュレーションデータだが、スタイリング担当の
実入稿データが無い段階では、実商品（`data/products.json`。9中分類・9,180件）から
**決定的**に組んだ「暫定コーディネート」で代替する（**暫定・実コーデ差し替え口**。
将来スタイリング担当の入稿データが揃い次第、本モジュールを経由せず `coordinates.json` を
直接差し替えればよい。`RecommenderInterface`／`HybridRecommender` は生成後の
`coordinates.json` の形（coordinate_id/product_ids/...）にのみ依存するため、差し替えても
実装への影響はない）。

## 選定方針（曖昧仕様の採用理由。要件定義書14章の前提として採用）
各テーマ（`COORDINATE_SPECS`）は「中分類・開始オフセット・件数」の組で構成され、対象中分類の
商品を **product_id 昇順**（ソースデータで既に一意・安定なキー。`batch/product_codes.py` の
個別番号採番と同じ安定順の採用理由）で並べた先頭から `[start:start+count]` を選ぶ。
これにより同一入力（`products.json`）から常に同一の `coordinates.json` が再現される。

9中分類すべてが最低1回はいずれかのセットに登場するよう `COORDINATE_SPECS` を構成し、
`co_purchase_source.json`（段階B2で実9中分類に合わせて再構成した併売スコア）が重視する
「リビング回遊を促す組合せ」（ソファ×クッション×ラグ、テーブル×チェア 等）と一致するテーマを
中心に据える。

## 責務分離
- `build_coordinates(products, specs) -> coordinates` … 純粋関数。I/Oに触れず、テスト容易性を担保する。
- `load_products()` / `write_coordinates()` … I/O。
- `run()` … 上記を束ねるオーケストレーション（CLIからも呼ばれる）。

## CLI
    cd backend
    .venv\\Scripts\\python.exe -m ingest.build_coordinates
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NamedTuple, Optional, Union

from dataio import DEFAULT_DATA_DIR, load_json_list

PRODUCTS_FILENAME = "products.json"
COORDINATES_FILENAME = "coordinates.json"


class Pick(NamedTuple):
    """1つのコーディネートに組み込む「中分類・開始オフセット・件数」の指定。"""

    cat_mid: str
    start: int
    count: int


class CoordinateSpec(NamedTuple):
    coordinate_id: str
    name: str
    theme: str
    picks: tuple[Pick, ...]


# 段階B2: 実9中分類（products.json の cat_mid）を対象にした暫定コーディネート6セット。
# 全9中分類が最低1回登場する（下記コメントの通り）。
COORDINATE_SPECS: tuple[CoordinateSpec, ...] = (
    CoordinateSpec(
        coordinate_id="C001",
        name="モダンリビングセット",
        theme="モダン",
        picks=(
            Pick("ソファ", 0, 1),
            Pick("テーブル", 0, 1),
            Pick("カーペット・ラグ・マット", 0, 1),
            Pick("クッション・カバー", 0, 1),
        ),
    ),
    CoordinateSpec(
        coordinate_id="C002",
        name="北欧ダイニング",
        theme="北欧",
        picks=(
            Pick("テーブル", 1, 1),
            Pick("椅子・チェア", 0, 2),
        ),
    ),
    CoordinateSpec(
        coordinate_id="C003",
        name="リラックスソファ＋間接照明",
        theme="アーバン",
        picks=(
            Pick("ソファ", 1, 1),
            Pick("ライト・照明器具", 0, 1),
            Pick("クッション・カバー", 1, 2),
        ),
    ),
    CoordinateSpec(
        coordinate_id="C004",
        name="収納＆テレビボードコーナー",
        theme="シンプル",
        picks=(
            Pick("テレビ台・リビング収納・仏壇", 0, 1),
            Pick("収納家具", 0, 2),
        ),
    ),
    CoordinateSpec(
        coordinate_id="C005",
        name="カーテン＆クッションコーディネート",
        theme="ナチュラル",
        picks=(
            Pick("カーテン", 0, 2),
            Pick("クッション・カバー", 2, 1),
        ),
    ),
    CoordinateSpec(
        coordinate_id="C006",
        name="寛ぎのリビング（フロア横断コーデ）",
        theme="アーバン",
        picks=(
            Pick("ソファ", 2, 1),
            Pick("カーペット・ラグ・マット", 1, 1),
            Pick("ライト・照明器具", 1, 1),
            Pick("テーブル", 2, 1),
        ),
    ),
)


def _group_by_mid_sorted(products: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """`cat_mid` -> `product_id` 昇順に並べた商品リスト、の索引を作る（純粋関数）。"""
    by_mid: dict[str, list[dict[str, Any]]] = {}
    for p in products:
        by_mid.setdefault(p.get("cat_mid"), []).append(p)
    for mid, members in by_mid.items():
        by_mid[mid] = sorted(members, key=lambda p: p["product_id"])
    return by_mid


def build_coordinates(
    products: list[dict[str, Any]], specs: tuple[CoordinateSpec, ...] = COORDINATE_SPECS
) -> list[dict[str, Any]]:
    """products（`cat_mid`/`product_id`/`price` を持つ辞書のリスト）から
    `coordinates.json` 相当のレコードリストを決定的に組み立てる（純粋関数）。

    Raises:
        ValueError: 指定した中分類・件数に対して実商品が不足している場合
            （データ不整合をサイレントに無視せず例外にする）。
    """
    by_mid = _group_by_mid_sorted(products)

    result: list[dict[str, Any]] = []
    for spec in specs:
        product_ids: list[str] = []
        total_price = 0
        for pick in spec.picks:
            candidates = by_mid.get(pick.cat_mid, [])
            selected = candidates[pick.start : pick.start + pick.count]
            if len(selected) < pick.count:
                raise ValueError(
                    f"コーディネート {spec.coordinate_id} の中分類 {pick.cat_mid!r} の"
                    f"在庫が不足しています（必要 {pick.count} 件、start={pick.start} 以降の"
                    f"実在 {len(selected)} 件）。"
                )
            for product in selected:
                product_ids.append(product["product_id"])
                total_price += int(product.get("price", 0))

        result.append(
            {
                "coordinate_id": spec.coordinate_id,
                "name": spec.name,
                "theme": spec.theme,
                "product_ids": product_ids,
                # 暫定・実コーデ差し替え口: 完成イメージ画像は未入稿のためダミー画像。
                "image_url": (
                    f"https://dummyimage.com/600x400/dddddd/333333&text={spec.coordinate_id}"
                ),
                "total_price_estimate": total_price,
            }
        )

    return result


def load_products(data_dir: Optional[Union[str, Path]] = None) -> list[dict[str, Any]]:
    return load_json_list(PRODUCTS_FILENAME, data_dir=data_dir)


def write_coordinates(
    coordinates: list[dict[str, Any]], data_dir: Optional[Union[str, Path]] = None
) -> Path:
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    path = base / COORDINATES_FILENAME
    path.write_text(json.dumps(coordinates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run(
    data_dir: Optional[Union[str, Path]] = None,
    specs: Optional[tuple[CoordinateSpec, ...]] = None,
) -> dict[str, int]:
    """バッチ本体: 読み込み→構築→書き出しを行い、件数サマリを返す。

    Args:
        specs: テスト容易性のため差し替え可能（未指定時は既定の `COORDINATE_SPECS`。
            実データの9中分類を前提とするため、旧サンプル体系のフィクスチャに対しては
            テスト側で別の `specs` を渡して検証する）。
    """
    products = load_products(data_dir=data_dir)
    coordinates = build_coordinates(products, specs if specs is not None else COORDINATE_SPECS)
    write_coordinates(coordinates, data_dir=data_dir)
    return {"generated": len(coordinates)}


def main() -> None:
    summary = run()
    print(f"coordinates.json を生成しました（暫定・実商品構成）: {summary['generated']} 件")


if __name__ == "__main__":
    main()
