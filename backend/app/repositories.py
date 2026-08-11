"""読み取り専用データ参照層（6章 データモデル / DESIGN.md 2章）。

`data/` 配下のJSON（products / qr_codes / coordinates / store_map）を
`dataio.load_json_list` / `load_json_dict`（欠損時フォールバック済み）経由で読み込み、
IDでの引き当てをできるようにする薄いリポジトリ群。API層（routers）はこれらを通じてのみ
サンプル/実データにアクセスし、JSONファイルの詳細を知らなくてよいようにする
（責務分離：データ層／ロジック層／UI層）。

いずれも `from_data_dir()` でテスト用の別データディレクトリに差し替え可能。
"""
from __future__ import annotations

import re
from typing import Any, Optional, Union
from pathlib import Path

from dataio import load_json_dict, load_json_list


def normalize_product_code(code: str) -> str:
    """商品番号（`LL-MM-SS-NNNN`）の入力を突合用に正規化する。

    新機能「商品番号による直接遷移」（要件4.1 カメラ非対応フォールバックの拡張）:
    表示はハイフン区切りだが、来店客の入力は**ハイフン有無どちらも許容**する仕様
    （`backend/batch/product_codes.py` docstring参照）。数字以外の文字（ハイフン・
    空白等）をすべて取り除いた数字列に正規化することで、"01-03-02-0001" と
    "0103020001" のどちらでも同一商品に解決できるようにする（桁数自体は採番バッチ側の
    体系（段階B1で個別番号を3桁→4桁へ拡張）に依存し、本関数は桁数を問わず数字のみへ
    正規化するだけなので、桁数変更による影響を受けない）。
    """
    return re.sub(r"[^0-9]", "", code)


class ProductRepository:
    """商品マスタ（products.json）。"""

    def __init__(self, products: list[dict[str, Any]]):
        self._by_id = {p["product_id"]: p for p in products if "product_id" in p}
        # 商品番号（product_code）→商品 の索引。正規化（ハイフン除去）した数字列をキーにする。
        self._by_code = {
            normalize_product_code(p["product_code"]): p
            for p in products
            if p.get("product_code")
        }

    @classmethod
    def from_data_dir(
        cls, data_dir: Optional[Union[str, Path]] = None
    ) -> "ProductRepository":
        return cls(load_json_list("products.json", data_dir=data_dir))

    def get(self, product_id: str) -> Optional[dict[str, Any]]:
        return self._by_id.get(product_id)

    def get_by_code(self, code: str) -> Optional[dict[str, Any]]:
        """商品番号（ハイフン有無どちらでも可）から商品を引き当てる。"""
        return self._by_code.get(normalize_product_code(code))

    def all(self) -> list[dict[str, Any]]:
        return list(self._by_id.values())


class QrRepository:
    """QRマスタ（qr_codes.json）。"""

    def __init__(self, qr_codes: list[dict[str, Any]]):
        self._by_id = {q["qr_id"]: q for q in qr_codes if "qr_id" in q}
        # 商品QR（type=="product"）を product_id から引き当てる索引。
        # 新機能「商品番号による直接遷移」で、解決した product_id に対応する
        # qr_id を求めるために使う（＝その商品QRをスキャンしたのと等価にするため）。
        self._by_product_id = {
            q["product_id"]: q
            for q in qr_codes
            if q.get("type") == "product" and q.get("product_id")
        }

    @classmethod
    def from_data_dir(cls, data_dir: Optional[Union[str, Path]] = None) -> "QrRepository":
        return cls(load_json_list("qr_codes.json", data_dir=data_dir))

    def get(self, qr_id: str) -> Optional[dict[str, Any]]:
        return self._by_id.get(qr_id)

    def get_by_product_id(self, product_id: str) -> Optional[dict[str, Any]]:
        """指定した商品の商品QR（type=="product"）を引き当てる。"""
        return self._by_product_id.get(product_id)


class CoordinateRepository:
    """コーディネートマスタ（coordinates.json）。"""

    def __init__(self, coordinates: list[dict[str, Any]]):
        self._by_id = {c["coordinate_id"]: c for c in coordinates if "coordinate_id" in c}

    @classmethod
    def from_data_dir(
        cls, data_dir: Optional[Union[str, Path]] = None
    ) -> "CoordinateRepository":
        return cls(load_json_list("coordinates.json", data_dir=data_dir))

    def get(self, coordinate_id: str) -> Optional[dict[str, Any]]:
        return self._by_id.get(coordinate_id)


class StoreMapRepository:
    """店舗マップ（store_map.json）。フロア単位で引き当てる。"""

    def __init__(self, store_map: dict[str, Any]):
        self._floors = {f["floor"]: f for f in store_map.get("floors", []) if "floor" in f}

    @classmethod
    def from_data_dir(
        cls, data_dir: Optional[Union[str, Path]] = None
    ) -> "StoreMapRepository":
        return cls(load_json_dict("store_map.json", data_dir=data_dir))

    def get_floor(self, floor: int) -> Optional[dict[str, Any]]:
        return self._floors.get(floor)

    def floors(self) -> list[int]:
        return sorted(self._floors.keys())
