"""配布版の同一プロセス静的配信に関する回帰テスト。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.frontend import SpaStaticFiles, mount_bundled_frontend


def _make_dist(path: Path) -> Path:
    path.mkdir()
    (path / "index.html").write_text(
        "<!doctype html><title>Room Harmony packaged</title>", encoding="utf-8"
    )
    (path / "asset.js").write_text("console.log('ok')", encoding="utf-8")
    return path


def test_spa_routes_fall_back_but_missing_assets_and_api_do_not(tmp_path: Path) -> None:
    app = FastAPI()
    app.mount("/", SpaStaticFiles(_make_dist(tmp_path / "dist")))
    client = TestClient(app)

    route_response = client.get("/s/QR-PRODUCT-01")
    assert route_response.status_code == 200
    assert "Room Harmony packaged" in route_response.text
    assert route_response.headers["cache-control"] == "no-cache"

    assert client.get("/asset.js").status_code == 200
    assert client.get("/missing.js").status_code == 404
    assert client.get("/api/not-real").status_code == 404


def test_mount_is_disabled_without_release_flag(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ROOM_HARMONY_SERVE_FRONTEND", raising=False)
    monkeypatch.setenv("FRONTEND_DIST_DIR", str(_make_dist(tmp_path / "dist")))
    app = FastAPI()

    mount_bundled_frontend(app)

    assert TestClient(app).get("/").status_code == 404


def test_mount_requires_a_real_index_in_release_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ROOM_HARMONY_SERVE_FRONTEND", "1")
    monkeypatch.setenv("FRONTEND_DIST_DIR", str(tmp_path / "missing"))
    app = FastAPI()

    try:
        mount_bundled_frontend(app)
    except RuntimeError as exc:
        assert "index.html" in str(exc)
    else:
        raise AssertionError("missing release frontend must fail fast")
