"""データ層（サンプル/実データの読み込み・欠損時フォールバック）。

`recommender` / `routing` のロジック層は、本パッケージの関数か、テスト容易性のための
データ注入コンストラクタのいずれかを通じてデータを受け取る。ロジック層自身はファイル
パスやJSON構造の詳細を知らなくてよいようにし、責務分離（データ層／ロジック層）を保つ。
"""
from .loader import DEFAULT_DATA_DIR, load_json_dict, load_json_list

__all__ = ["DEFAULT_DATA_DIR", "load_json_dict", "load_json_list"]
