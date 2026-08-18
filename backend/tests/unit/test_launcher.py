"""自包含デモ起動器の資源検査・ポート競合・多重起動判定テスト。"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

import launcher


def _runtime_paths(root: Path) -> launcher.RuntimePaths:
    app_data = root / "app-data"
    runtime = app_data / "runtime"
    return launcher.RuntimePaths(
        resource_root=root,
        data_dir=root / "data",
        frontend_dir=root / "frontend_dist",
        app_data_dir=app_data,
        runtime_dir=runtime,
        database_path=app_data / "data" / "room_harmony.db",
        state_path=runtime / "instance.json",
        log_path=runtime / "launcher.log",
        diagnostics_path=app_data / "diagnostics.txt",
    )


def _write_valid_resources(paths: launcher.RuntimePaths) -> None:
    paths.frontend_dir.mkdir(parents=True)
    (paths.frontend_dir / "index.html").write_text("Room Harmony", encoding="utf-8")
    paths.data_dir.mkdir(parents=True)
    payloads = {
        "products.json": [
            {
                "product_id": "demo-product",
                "product_code": "01-02-01-0799",
            }
        ],
        "qr_codes.json": [{"qr_id": "QR-ENTRANCE-001"}],
        "coordinates.json": [{"coordinate_id": "C001"}],
        "store_map.json": {"floors": [{"floor": 1}]},
        "co_purchase.json": [{"from": "a", "to": "b"}],
        "member_history.json": {"members": []},
        "pos_metrics.json": {"control": {}},
        "aggregates.json": {"customer_total": 0},
    }
    for filename, value in payloads.items():
        (paths.data_dir / filename).write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8"
        )


def test_validate_resources_accepts_complete_release(tmp_path: Path) -> None:
    paths = _runtime_paths(tmp_path)
    _write_valid_resources(paths)

    report = launcher.validate_resources(paths)

    assert report["counts"]["products.json"] == 1
    assert report["frontend_index"].endswith("index.html")


def test_validate_resources_reports_all_obvious_release_damage(tmp_path: Path) -> None:
    paths = _runtime_paths(tmp_path)
    _write_valid_resources(paths)
    (paths.frontend_dir / "index.html").unlink()
    (paths.data_dir / "products.json").write_text("not json", encoding="utf-8")
    (paths.data_dir / "store_map.json").write_text('{"floors": []}', encoding="utf-8")

    with pytest.raises(RuntimeError) as exc_info:
        launcher.validate_resources(paths)

    message = str(exc_info.value)
    assert "Frontend index is missing" in message
    assert "products.json" in message
    assert "store_map.json has no floors" in message


def test_port_conflict_falls_back_without_touching_the_owner() -> None:
    owner = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    owner.bind(("127.0.0.1", 0))
    occupied_port = int(owner.getsockname()[1])
    reserved = launcher._reserve_loopback_socket(occupied_port)
    try:
        assert int(reserved.getsockname()[1]) != occupied_port
        assert owner.getsockname()[1] == occupied_port
    finally:
        reserved.close()
        owner.close()


def test_existing_instance_requires_matching_instance_id(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "instance.json"
    state_path.write_text(
        json.dumps({"url": "http://127.0.0.1:8123", "instance_id": "ours"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        launcher,
        "_http_json",
        lambda _url: {"status": "ok", "instance_id": "someone-else"},
    )

    assert launcher.find_existing_instance(state_path) is None
    assert not state_path.exists()


def test_existing_instance_is_reused_only_after_live_health_match(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "instance.json"
    state_path.write_text(
        json.dumps({"url": "http://127.0.0.1:8123", "instance_id": "ours"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        launcher,
        "_http_json",
        lambda _url: {"status": "ok", "instance_id": "ours"},
    )

    assert launcher.find_existing_instance(state_path) == "http://127.0.0.1:8123"
    assert state_path.exists()


def test_packaged_demo_always_enables_guided_chat(monkeypatch, tmp_path: Path) -> None:
    paths = _runtime_paths(tmp_path)
    monkeypatch.setenv("EXPERIMENT_GROUP_MODE", "fixed")
    monkeypatch.setenv("EXPERIMENT_GROUP_RATIO", "0")

    launcher._set_runtime_environment(paths, "instance-id")

    assert os.environ["EXPERIMENT_GROUP_MODE"] == "random"
    assert os.environ["EXPERIMENT_GROUP_RATIO"] == "1.0"
