"""`app.openapi()` を `docs/openapi.json` に書き出すスクリプト（17章・step6 TS型生成の元）。

実行方法（cwd=backend）:
    .venv\\Scripts\\python.exe scripts/export_openapi.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# backend/scripts/export_openapi.py から見て backend/ を import path に追加する
# （`app` パッケージを `pytest.ini` の pythonpath 設定なしでも解決できるようにするため）。
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.main import app  # noqa: E402  (sys.path 設定後に import する必要があるため)


def main() -> Path:
    schema = app.openapi()
    out_path = _BACKEND_DIR.parent / "docs" / "openapi.json"
    out_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    return out_path


if __name__ == "__main__":
    main()
