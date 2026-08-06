"""data/ 配下のサンプル/実データJSONを読み込む共通ローダ。

欠損時フォールバック（DECISIONS.md #5 の方針を全ファイルに準用）：
ファイルが存在しない・空・壊れたJSONであっても例外を投げず、安全なデフォルト
（配列なら空リスト、辞書なら既定値）を返す。これにより `recommender` / `routing`
はサンプルデータが未投入の状態でも起動時エラーにならない。
"""
import json
from pathlib import Path
from typing import Any, Optional, Union

# backend/dataio/loader.py から見て ../../data が既定のデータディレクトリ
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _read_text(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return text


def load_json_list(
    filename: str, data_dir: Optional[Union[str, Path]] = None
) -> list[dict[str, Any]]:
    """JSON配列ファイルを読み込む。存在しない/空/不正/配列でない場合は空リストを返す。"""
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    text = _read_text(base / filename)
    if text is None or not text.strip():
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def load_json_dict(
    filename: str,
    default: Optional[dict[str, Any]] = None,
    data_dir: Optional[Union[str, Path]] = None,
) -> dict[str, Any]:
    """JSONオブジェクトファイルを読み込む。存在しない/空/不正/オブジェクトでない場合は既定値を返す。"""
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    default_value = dict(default) if default is not None else {}
    text = _read_text(base / filename)
    if text is None or not text.strip():
        return default_value
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return default_value
    return data if isinstance(data, dict) else default_value


def load_aggregates(data_dir: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    """集計3指標（客総数・店舗数・会員数）を読み込む。欠損時は None フォールバック。

    DECISIONS.md #5: 会員データは今回扱わず、集計3指標のみを参照する。
    無い場合も全機能が動くよう、値は None を許容する。
    """
    default = {"customer_total": None, "store_count": None, "member_count": None}
    data = load_json_dict("aggregates.json", default=default, data_dir=data_dir)
    return {
        "customer_total": data.get("customer_total"),
        "store_count": data.get("store_count"),
        "member_count": data.get("member_count"),
    }
