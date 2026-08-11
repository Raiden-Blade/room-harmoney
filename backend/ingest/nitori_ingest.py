"""ニトリ実商品CSV → `data/products.json` 変換アダプタ（段階B1: 実データ投入）。

`data/source/*.csv`（9ファイル。ファイル毎に「カテゴリ」列＝中分類が1種類。列は共通で
`商品コード, 商品名, 価格（税込）, URL, 画像URL, カテゴリ, ブランド`）を読み込み、
`products.json` のスキーマ（`backend/batch/product_codes.py` が `product_code` を後付けする
前段の形）へ変換する。実サイトの自動収集は行わず、手動取得済みCSVの変換のみを担う
（`backend/ingest/__init__.py` の既存方針・DECISIONS.md #3 を踏襲）。

## 曖昧仕様の採用理由（要件定義書14章「未確定事項」の前提として採用。理由をここに残す）

- **小分類**: 実データCSVには小分類が無く、中分類（カテゴリ列）までしか粒度が無いため、
  `cat_small = cat_mid` とする（小分類レベルの絞り込みUIが機能しなくなるわけではなく、
  「小分類=中分類」という1階層少ない体系として扱う）。
- **大分類**: 中分類9種を「家具／ファブリック／照明」の3大分類へ手動マッピングする
  （`MID_TO_LARGE`）。ニトリの実サイト側の大分類体系が本CSVに含まれていないための代替。
- **価格**: 「〜」区切りの範囲価格（セット商品でカラー等により価格が変動するもの）は
  来店客が実際に手に取れる最安構成を提示する意図で**下限値**を採用する。
- **色**: 商品名からのキーワード抽出（商品説明やカラーバリエーション列が無いため）。複合色
  （例: ライトグレー）は単色（グレー）の部分文字列を含むため、`COLOR_KEYWORDS` の並び順
  （複合色を先に判定）がそのまま抽出の優先順位になる。
- **売場位置（floor/zone/x/y）**: 什器配置台帳等の実測データが無いため、中分類単位で
  `data/store_map.json` の実在ノード（1件）に代表点として割当てる（`assign_location`）。
  これにより同一中分類の全商品が同一ノード上に載るが、経路探索・QR位置表示は中分類の
  実在ノードに対して常に解決可能になる（＝「商品がルート可能なノード上に載る」という
  ゲート条件を満たす）。将来、什器単位の実測座標が得られ次第、商品ごとに個別ノードへ
  割当て直せる（本モジュールの `assign_location` を商品単位の入力に差し替えるだけでよい
  設計＝責務分離）。

## 責務分離
- `parse_price` / `extract_color` / `resolve_waypoint_location` / `assign_location` /
  `build_products` … 純粋関数。I/Oに触れず、テスト容易性を担保する。
- `load_store_map` / `write_products` / `_iter_source_csv_rows` … I/O。
- `run()` … 上記を束ねるオーケストレーション（CLIからも呼ばれる）。

## CLI
    cd backend
    .venv\\Scripts\\python.exe -m ingest.nitori_ingest

`data/source/*.csv` を読み `data/products.json` を上書き生成する（既存 `product_code` 列は
本モジュールでは付与しない。付与は後続の `python -m batch.product_codes` で行う）。
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Optional, Union

from dataio import DEFAULT_DATA_DIR

SOURCE_DIRNAME = "source"
PRODUCTS_FILENAME = "products.json"
STORE_MAP_FILENAME = "store_map.json"

# 大分類マップ（中分類→大分類）。9中分類は data/source/*.csv の「カテゴリ」列（ファイル毎に
# 1種類）と一致する（実装指示より）。
MID_TO_LARGE: dict[str, str] = {
    "ソファ": "家具",
    "椅子・チェア": "家具",
    "テーブル": "家具",
    "テレビ台・リビング収納・仏壇": "家具",
    "収納家具": "家具",
    "カーペット・ラグ・マット": "ファブリック",
    "カーテン": "ファブリック",
    "クッション・カバー": "ファブリック",
    "ライト・照明器具": "照明",
}

# サブ通路（付帯品）フラグを立てる中分類（実装指示より: クッション・カバー / ライト・照明器具）。
SUB_PASSAGE_MIDS: frozenset[str] = frozenset({"クッション・カバー", "ライト・照明器具"})

# 中分類 → data/store_map.json 上の実在ウェイポイントID。9中分類を4フロアへ分散しつつ、
# サブ通路指定の2中分類は「サブ通路」型ノードへ、他は「商品近傍」型ノードへ割当てる。
# （すべて data/store_map.json に実在するノードID。`test_nitori_ingest.py` /
#  `test_sample_data_integrity.py` 相当の整合チェックは本モジュールの単体テストで検証する。）
MID_TO_WAYPOINT_ID: dict[str, str] = {
    # 1F: ソファ・椅子（家具の主力アイテムを入口階に配置）
    "ソファ": "f1_wp_P001",
    "椅子・チェア": "f1_wp_P004",
    # 2F: テーブル・テレビ台等の据置家具
    "テーブル": "f2_wp_P011",
    "テレビ台・リビング収納・仏壇": "f2_wp_P016",
    # 3F: 収納家具・カーペット
    "収納家具": "f3_wp_P020",
    "カーペット・ラグ・マット": "f3_wp_P024",
    # 4F: カーテン（通常ゾーン）、クッション・照明（サブ通路＝付帯品扱い）
    "カーテン": "f4_wp_P029",
    "クッション・カバー": "f1_subpassage",
    "ライト・照明器具": "f4_subpassage",
}

# 商品名から色を抽出するキーワード（優先順）。複合色（例: ライトグレー／ダークブラウン）は
# その部分文字列である単色（グレー／ブラウン）より必ず先に判定する必要があるため、
# この並び順自体が抽出仕様である。
COLOR_KEYWORDS: tuple[str, ...] = (
    "ライトグレー",
    "ダークグレー",
    "ライトブラウン",
    "ダークブラウン",
    "グレージュ",
    "ホワイト",
    "ブラック",
    "グレー",
    "ナチュラル",
    "ベージュ",
    "アイボリー",
    "ブラウン",
    "ネイビー",
    "ブルー",
    "グリーン",
    "レッド",
    "ピンク",
    "イエロー",
    "オレンジ",
    "パープル",
    "モカ",
    "カーキ",
    "シルバー",
    "ゴールド",
    "オーク",
    "ウォールナット",
)

_PRICE_DIGITS_RE = re.compile(r"\d+")


def parse_price(raw: Optional[str]) -> int:
    """価格文字列（例: "30990円" / "37990～47990円" / "1,234円"）から価格（int）を抽出する。

    純粋関数。範囲価格（"〜"/"～"区切り）は最初に現れる数字＝下限値を採用する
    （来店客が実際に選べる最安構成を示す意図。モジュールdocstring「曖昧仕様の採用理由」参照）。
    カンマは桁区切りとして除去する。数字が1つも含まれない場合は 0（安全側フォールバック）。
    """
    if not raw:
        return 0
    cleaned = raw.replace(",", "")
    match = _PRICE_DIGITS_RE.search(cleaned)
    if match is None:
        return 0
    return int(match.group())


def extract_color(name: Optional[str]) -> str:
    """商品名から色キーワードを抽出する（純粋関数）。`COLOR_KEYWORDS` の並び順で最初に一致した
    ものを返す。一致が無ければ ""。"""
    if not name:
        return ""
    for color in COLOR_KEYWORDS:
        if color in name:
            return color
    return ""


def resolve_waypoint_location(waypoint_id: str, store_map: dict[str, Any]) -> dict[str, Any]:
    """`store_map.json`（辞書）から指定ウェイポイントの `floor/x/y/zone` を求める（純粋関数）。

    - ウェイポイント自身が「サブ通路」型ノードの場合: そのまま zone="SUB" を返す。
    - それ以外: そのノードに直接接続する（`edges` の from/to どちらか）「ゾーン」型ノードを
      探し、そのノードID末尾の1文字（例: "f1_zoneA" → "A"）をゾーン記号とする。接続先が
      「サブ通路」型ノードの場合は zone="SUB" とする（商品近傍ノードがサブ通路ハブに
      直結しているケース。既存サンプルデータの慣習に合わせる）。

    Raises:
        KeyError: waypoint_id が store_map のどのフロアにも存在しない場合。
        ValueError: 見つかった waypoint がゾーン/サブ通路ノードに接続していない場合
            （店舗マップ側のデータ不整合。サイレントに無視せず例外にする）。
    """
    for floor_obj in store_map.get("floors", []):
        by_id = {w["id"]: w for w in floor_obj.get("waypoints", [])}
        wp = by_id.get(waypoint_id)
        if wp is None:
            continue

        if wp.get("type") == "サブ通路":
            return {"floor": wp["floor"], "x": wp["x"], "y": wp["y"], "zone": "SUB"}

        for edge in floor_obj.get("edges", []):
            if edge.get("from") == waypoint_id:
                other_id = edge.get("to")
            elif edge.get("to") == waypoint_id:
                other_id = edge.get("from")
            else:
                continue
            other = by_id.get(other_id)
            if other is None:
                continue
            if other.get("type") == "ゾーン":
                return {
                    "floor": wp["floor"],
                    "x": wp["x"],
                    "y": wp["y"],
                    "zone": other["id"][-1],
                }
            if other.get("type") == "サブ通路":
                return {"floor": wp["floor"], "x": wp["x"], "y": wp["y"], "zone": "SUB"}

        raise ValueError(
            f"waypoint '{waypoint_id}' はゾーン/サブ通路ノードに接続していません（store_map不整合）。"
        )

    raise KeyError(f"waypoint_id '{waypoint_id}' が store_map に見つかりません。")


def assign_location(mid: str, store_map: dict[str, Any]) -> dict[str, Any]:
    """中分類 → `store_map.json` 上の実在ノードの `floor/x/y/zone` を返す（純粋関数）。

    商品ごとの実測什器座標データが無いため、同一中分類の商品は同一ノード（売場代表点）を
    共有する前提を採用する（モジュールdocstring「曖昧仕様の採用理由」参照）。

    Raises:
        KeyError: `mid` に対する割当て（`MID_TO_WAYPOINT_ID`）が定義されていない場合。
    """
    if mid not in MID_TO_WAYPOINT_ID:
        raise KeyError(f"未知の中分類です（waypoint割当て未定義）: {mid!r}")
    return resolve_waypoint_location(MID_TO_WAYPOINT_ID[mid], store_map)


def build_products(
    rows: list[tuple[str, dict[str, str]]], store_map: dict[str, Any]
) -> list[dict[str, Any]]:
    """CSV行（`(ファイル名, 行dict)` のリスト）→ products.json のレコードリストへ変換する
    （純粋関数）。

    dedup: 商品コード（`商品コード`列）が重複する場合、`rows` の並び順で先に現れたものを
    採用する（＝呼び出し側がファイル名昇順・ファイル内はCSVの行順で渡せば「ファイル名昇順で
    先勝ち」になる。決定的）。出力の並び順も、この「先に採用された順」（＝入力の走査順）を
    そのまま保持するため、同一入力から常に同一順序の出力になる（再現性）。

    Raises:
        KeyError: 行の「カテゴリ」列が `MID_TO_LARGE` / `MID_TO_WAYPOINT_ID` に無い未知の
            中分類の場合（サイレントに無視せず例外にする）。
    """
    location_cache: dict[str, dict[str, Any]] = {}
    seen: dict[str, dict[str, Any]] = {}

    for _filename, row in rows:
        code = (row.get("商品コード") or "").strip()
        if not code or code in seen:
            continue

        mid = (row.get("カテゴリ") or "").strip()
        if mid not in MID_TO_LARGE:
            raise KeyError(f"未知の中分類です（大分類マップ未定義）: {mid!r}")

        if mid not in location_cache:
            location_cache[mid] = assign_location(mid, store_map)
        location = location_cache[mid]

        name = (row.get("商品名") or "").strip()
        seen[code] = {
            "product_id": code,
            "name": name,
            "price": parse_price(row.get("価格（税込）")),
            "image_url": (row.get("画像URL") or "").strip(),
            "source_url": (row.get("URL") or "").strip(),
            "brand": (row.get("ブランド") or "").strip(),
            "cat_large": MID_TO_LARGE[mid],
            "cat_mid": mid,
            "cat_small": mid,
            "color": extract_color(name),
            "floor": location["floor"],
            "zone": location["zone"],
            "x": location["x"],
            "y": location["y"],
            "sub_passage_flag": mid in SUB_PASSAGE_MIDS,
        }

    return list(seen.values())


def _iter_source_csv_rows(source_dir: Path) -> list[tuple[str, dict[str, str]]]:
    """`source_dir` 配下の `*.csv` をファイル名昇順に読み、`(ファイル名, 行dict)` を返す（I/O）。

    UTF-8 BOM付きファイルを想定し `utf-8-sig` で読む（BOMが残ると先頭列名 "商品コード" の
    照合に失敗するため）。
    """
    rows: list[tuple[str, dict[str, str]]] = []
    for path in sorted(source_dir.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append((path.name, row))
    return rows


def load_store_map(data_dir: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    text = (base / STORE_MAP_FILENAME).read_text(encoding="utf-8")
    return json.loads(text)


def write_products(
    products: list[dict[str, Any]], data_dir: Optional[Union[str, Path]] = None
) -> Path:
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    path = base / PRODUCTS_FILENAME
    path.write_text(json.dumps(products, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run(data_dir: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    """バッチ本体: `data/source/*.csv` 読み込み→変換→`products.json` 書き出しを行い、
    件数サマリ（総件数・中分類別件数）を返す。"""
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    store_map = load_store_map(data_dir=base)
    rows = _iter_source_csv_rows(base / SOURCE_DIRNAME)
    products = build_products(rows, store_map)
    write_products(products, data_dir=base)

    by_mid: dict[str, int] = {}
    for p in products:
        by_mid[p["cat_mid"]] = by_mid.get(p["cat_mid"], 0) + 1

    return {"total": len(products), "by_mid": by_mid}


def main() -> None:
    summary = run()
    print(f"products.json を生成しました（実データ投入）: 総 {summary['total']} 件")
    for mid, count in sorted(summary["by_mid"].items()):
        print(f"  {mid}: {count} 件")


if __name__ == "__main__":
    main()
