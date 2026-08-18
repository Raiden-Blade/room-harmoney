# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller specification for the self-contained demo."""
from pathlib import Path
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path.cwd().resolve()
BACKEND = ROOT / "backend"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DATA = ROOT / "data"
RELEASE_DATA_FILES = (
    "products.json",
    "qr_codes.json",
    "coordinates.json",
    "store_map.json",
    "co_purchase.json",
    "member_history.json",
    "pos_metrics.json",
    "aggregates.json",
)

for required in (BACKEND / "launcher.py", FRONTEND_DIST / "index.html", DATA / "products.json"):
    if not required.exists():
        raise SystemExit(f"Release input is missing: {required}")

hidden_imports = collect_submodules("uvicorn")

a = Analysis(
    [str(BACKEND / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=[
        *((str(DATA / filename), "data") for filename in RELEASE_DATA_FILES),
        (str(FRONTEND_DIST), "frontend_dist"),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # NetworkX exposes optional pandas/numpy conversion helpers, but Room Harmony's
    # routing path uses only its pure-Python graph algorithms. Excluding those optional
    # stacks removes thousands of unrelated files from the beginner download.
    excludes=["pytest", "playwright", "pandas", "numpy", "matplotlib", "IPython"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RoomHarmony",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collection = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="RoomHarmony",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collection,
        name="Room Harmony.app",
        icon=None,
        bundle_identifier="jp.roomharmony.demo",
        version=os.environ.get("ROOM_HARMONY_VERSION", "0.4.0"),
        info_plist={
            "CFBundleDisplayName": "Room Harmony",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
