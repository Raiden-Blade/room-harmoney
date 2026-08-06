"""読み取り専用データ参照層（6章 データモデル / DESIGN.md 2章）。

`data/` 配下のJSON（products / qr_codes / coordinates / store_map）を
`dataio.load_json_list` / `load_json_dict`（欠損時フォールバック済み）経由で読み込み、
IDでの引き当てをできるようにする薄いリポジトリ群。API層（routers）はこれらを通じてのみ
サンプル/実データにアクセスし、JSONファイルの詳細を知らなくてよいようにする
（責務分離：データ層／ロジック層／UI層）。

いずれも `from_data_dir()` でテスト用の別データディレクトリに差し替え可能。
"""
from __future__ import annotations

from typing import Any, Optional, Union
from pathlib import Path

from dataio import load_json_dict, load_json_list


class ProductRepository:
    """商品マスタ（products.json）。"""

    def __init__(self, products: list[dict[str, Any]]):
        self._by_id = {p["product_id"]: p for p in products if "product_id" in p}

    @classmethod
    def from_data_dir(
        cls, data_dir: Optional[Union[str, Path]] = None
    ) -> "ProductRepository":
        return cls(load_json_list("products.json", data_dir=data_dir))

    def get(self, product_id: str) -> Optional[dict[str, Any]]:
        return self._by_id.get(product_id)

    def all(self) -> list[dict[str, Any]]:
        return list(self._by_id.values())


class QrRepository:
    """QRマスタ（qr_codes.json）。"""

    def __init__(self, qr_codes: list[dict[str, Any]]):
        self._by_id = {q["qr_id"]: q for q in qr_codes if "qr_id" in q}

    @classmethod
    def from_data_dir(cls, data_dir: Optional[Union[str, Path]] = None) -> "QrRepository":
        return cls(load_json_list("qr_codes.json", data_dir=data_dir))

    def get(self, qr_id: str) -> Optional[dict[str, Any]]:
        return self._by_id.get(qr_id)


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
