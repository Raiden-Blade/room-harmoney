"""Room Harmony desktop demo launcher.

The release executable embeds Python, backend dependencies, the built frontend and
sample data. It binds only to loopback, verifies the actual HTTP responses, opens the
demo route, and keeps a small control window alive so beginners never need a terminal.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

APP_NAME = "RoomHarmony"
DEMO_PATH = "/s/QR-PRODUCT-01-02-01-0799"
REQUIRED_DATA = {
    "products.json": list,
    "qr_codes.json": list,
    "coordinates.json": list,
    "store_map.json": dict,
    "co_purchase.json": list,
    "member_history.json": dict,
    "pos_metrics.json": dict,
    "aggregates.json": dict,
}


@dataclass(frozen=True)
class RuntimePaths:
    resource_root: Path
    data_dir: Path
    frontend_dir: Path
    app_data_dir: Path
    runtime_dir: Path
    database_path: Path
    state_path: Path
    log_path: Path
    diagnostics_path: Path


@dataclass
class RunningServer:
    server: Any
    thread: threading.Thread
    reserved_socket: socket.socket
    url: str
    demo_url: str
    instance_id: str
    state_path: Path

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
        try:
            self.reserved_socket.close()
        except OSError:
            pass
        _remove_owned_state(self.state_path, self.instance_id)


def _resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve()
    return Path(__file__).resolve().parent.parent


def _app_data_dir() -> Path:
    override = os.environ.get("ROOM_HARMONY_APP_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "RoomHarmony"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "RoomHarmony"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share") / "room-harmony"


def resolve_runtime_paths() -> RuntimePaths:
    resource_root = _resource_root()
    frozen = bool(getattr(sys, "frozen", False))
    frontend_dir = (
        resource_root / "frontend_dist"
        if frozen
        else resource_root / "frontend" / "dist"
    )
    app_data_dir = _app_data_dir()
    runtime_dir = app_data_dir / "runtime"
    return RuntimePaths(
        resource_root=resource_root,
        data_dir=resource_root / "data",
        frontend_dir=frontend_dir,
        app_data_dir=app_data_dir,
        runtime_dir=runtime_dir,
        database_path=app_data_dir / "data" / "room_harmony.db",
        state_path=runtime_dir / "instance.json",
        log_path=runtime_dir / "launcher.log",
        diagnostics_path=app_data_dir / "diagnostics.txt",
    )


def validate_resources(paths: RuntimePaths) -> dict[str, Any]:
    errors: list[str] = []
    counts: dict[str, int] = {}

    index = paths.frontend_dir / "index.html"
    if not index.is_file():
        errors.append(f"Frontend index is missing: {index}")

    loaded: dict[str, Any] = {}
    for filename, expected_type in REQUIRED_DATA.items():
        path = paths.data_dir / filename
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            errors.append(f"Data file is missing: {path}")
            continue
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Data file cannot be read: {path} ({exc})")
            continue
        if not isinstance(value, expected_type):
            errors.append(f"Data shape is invalid: {path} (expected {expected_type.__name__})")
            continue
        loaded[filename] = value
        counts[filename] = len(value)

    products = loaded.get("products.json", [])
    if not products:
        errors.append("products.json is empty")
    elif not any(
        isinstance(product, dict)
        and product.get("product_id")
        and product.get("product_code") == "01-02-01-0799"
        for product in products
    ):
        errors.append("The packaged demo product 01-02-01-0799 is missing")

    store_map = loaded.get("store_map.json", {})
    if not isinstance(store_map.get("floors"), list) or not store_map["floors"]:
        errors.append("store_map.json has no floors")

    if errors:
        raise RuntimeError("Release resource validation failed:\n- " + "\n- ".join(errors))
    return {"counts": counts, "frontend_index": str(index)}


def _configure_logging(paths: RuntimePaths) -> None:
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(paths.log_path, encoding="utf-8")],
        force=True,
    )


def _write_diagnostics(
    paths: RuntimePaths,
    *,
    validation: Optional[dict[str, Any]] = None,
    smoke: Optional[dict[str, Any]] = None,
    url: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    paths.app_data_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "Room Harmony diagnostics",
        f"generated_at={datetime.now(timezone.utc).isoformat()}",
        f"platform={platform.platform()}",
        f"architecture={platform.machine()}",
        f"python={platform.python_version()}",
        f"frozen={bool(getattr(sys, 'frozen', False))}",
        f"executable={sys.executable}",
        f"resource_root={paths.resource_root}",
        f"data_dir={paths.data_dir}",
        f"frontend_dir={paths.frontend_dir}",
        f"app_data_dir={paths.app_data_dir}",
        f"database_path={paths.database_path}",
        f"url={url or ''}",
        f"validation={json.dumps(validation or {}, ensure_ascii=False, sort_keys=True)}",
        f"smoke={json.dumps(smoke or {}, ensure_ascii=False, sort_keys=True)}",
        f"error={error or ''}",
        f"log={paths.log_path}",
    ]
    paths.diagnostics_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _http_json(url: str, timeout: float = 2.0) -> Optional[dict[str, Any]]:
    # Local health checks must not be redirected through a corporate HTTP proxy.
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as response:
            if response.status != 200:
                return None
            value = json.loads(response.read().decode("utf-8"))
            return value if isinstance(value, dict) else None
    except (OSError, URLError, json.JSONDecodeError):
        return None


def _http_contains(url: str, needle: str, timeout: float = 3.0) -> bool:
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as response:
            return response.status == 200 and needle in response.read().decode("utf-8")
    except (OSError, URLError, UnicodeDecodeError):
        return False


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: Optional[dict[str, Any]] = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid response from {url}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object from {url}")
    return value


def run_end_to_end_smoke(base_url: str) -> dict[str, Any]:
    """Exercise the packaged QR -> recommendation -> chat -> route call path."""
    qr_id = "QR-PRODUCT-01-02-01-0799"
    product_id = "7017971s"
    session = _request_json(
        f"{base_url}/api/session",
        method="POST",
        payload={"qr_id": qr_id},
    )
    session_id = session.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError("Packaged session API did not return a session_id")
    if session.get("experiment_group") != "treatment":
        raise RuntimeError("Packaged demo did not select the guided-chat treatment group")

    product = _request_json(f"{base_url}/api/products/{product_id}")
    if product.get("product_id") != product_id:
        raise RuntimeError("Packaged product API returned the wrong demo product")

    query = urlencode({"product_id": product_id, "session_id": session_id})
    recommendations = _request_json(f"{base_url}/api/recommendations?{query}")
    related = recommendations.get("related")
    if not isinstance(related, list) or not related:
        raise RuntimeError("Packaged recommender returned no related products")
    first_related = related[0] if isinstance(related[0], dict) else {}
    related_product = first_related.get("product")
    target_id = (
        related_product.get("product_id")
        if isinstance(related_product, dict)
        else None
    )
    if not isinstance(target_id, str) or not target_id:
        raise RuntimeError("Packaged recommender returned an invalid product")

    chat = _request_json(
        f"{base_url}/api/chat/turn?{urlencode({'session_id': session_id})}",
        method="POST",
        payload={
            "product_id": product_id,
            "action": "start",
            "mode": "customer",
            "state": {"answered_question_ids": [], "preferences": {}},
        },
    )
    if not isinstance(chat.get("recommendations"), list) or not chat["recommendations"]:
        raise RuntimeError("Packaged guided chat returned no recommendations")

    route_query = urlencode(
        {
            "from_qr": qr_id,
            "to_product": target_id,
            "session_id": session_id,
        }
    )
    route = _request_json(f"{base_url}/api/route?{route_query}")
    if not isinstance(route.get("waypoints"), list) or not route["waypoints"]:
        raise RuntimeError("Packaged route API returned no waypoints")
    return {
        "session_id": session_id,
        "origin_product_id": product_id,
        "recommended_product_id": target_id,
        "waypoint_count": len(route["waypoints"]),
    }


def find_existing_instance(state_path: Path) -> Optional[str]:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        url = str(state["url"])
        instance_id = str(state["instance_id"])
    except (FileNotFoundError, OSError, KeyError, TypeError, json.JSONDecodeError):
        return None
    health = _http_json(f"{url}/health")
    if health and health.get("status") == "ok" and health.get("instance_id") == instance_id:
        return url
    try:
        state_path.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def _reserve_loopback_socket(preferred_port: int) -> socket.socket:
    for port in (preferred_port, 0):
        reserved = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            reserved.bind(("127.0.0.1", port))
            reserved.set_inheritable(True)
            return reserved
        except OSError:
            reserved.close()
    raise RuntimeError("No local TCP port is available for Room Harmony")


def _set_runtime_environment(paths: RuntimePaths, instance_id: str) -> None:
    paths.database_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["RH_DATA_DIR"] = str(paths.data_dir)
    os.environ["DATABASE_URL"] = f"sqlite:///{paths.database_path}"
    os.environ["FRONTEND_DIST_DIR"] = str(paths.frontend_dir)
    os.environ["ROOM_HARMONY_SERVE_FRONTEND"] = "1"
    os.environ["ROOM_HARMONY_INSTANCE_ID"] = instance_id
    # A demo must deterministically show the guided-chat treatment flow.
    os.environ["EXPERIMENT_GROUP_MODE"] = "random"
    os.environ["EXPERIMENT_GROUP_RATIO"] = "1.0"


def start_server(paths: RuntimePaths, preferred_port: int = 8000) -> RunningServer:
    instance_id = uuid.uuid4().hex
    _set_runtime_environment(paths, instance_id)

    # Import only after all resource/database environment variables are final.
    import uvicorn
    from app.main import app

    reserved_socket = _reserve_loopback_socket(preferred_port)
    port = int(reserved_socket.getsockname()[1])
    url = f"http://127.0.0.1:{port}"
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [reserved_socket]},
        name="room-harmony-server",
        daemon=True,
    )
    thread.start()

    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        health = _http_json(f"{url}/health")
        if health and health.get("instance_id") == instance_id:
            break
        if not thread.is_alive():
            raise RuntimeError("Room Harmony server stopped during startup")
        time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("Room Harmony did not pass its health check within 45 seconds")

    demo_url = f"{url}{DEMO_PATH}"
    if not _http_contains(demo_url, "Room Harmony"):
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("The frontend did not pass its HTTP startup check")

    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.state_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "url": url,
                "instance_id": instance_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return RunningServer(
        server=server,
        thread=thread,
        reserved_socket=reserved_socket,
        url=url,
        demo_url=demo_url,
        instance_id=instance_id,
        state_path=paths.state_path,
    )


def _remove_owned_state(state_path: Path, instance_id: str) -> None:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("instance_id") == instance_id:
            state_path.unlink(missing_ok=True)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        pass


def _open_file(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _run_control_window(runtime: RunningServer, paths: RuntimePaths, no_browser: bool) -> int:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Room Harmony")
    root.geometry("520x285")
    root.resizable(False, False)
    root.configure(background="#202124")

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("RH.TFrame", background="#202124")
    style.configure("RH.TLabel", background="#202124", foreground="#f1f3f4", font=("Arial", 11))
    style.configure("Title.RH.TLabel", font=("Arial", 20, "bold"))
    style.configure("Status.RH.TLabel", foreground="#81c995", font=("Arial", 12, "bold"))
    style.configure("RH.TButton", font=("Arial", 10), padding=(12, 8))

    frame = ttk.Frame(root, style="RH.TFrame", padding=28)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Room Harmony", style="Title.RH.TLabel").pack(anchor="w")
    ttk.Label(frame, text="● デモは正常に起動しています", style="Status.RH.TLabel").pack(anchor="w", pady=(15, 6))
    ttk.Label(
        frame,
        text="この小さな画面を開いたまま、ブラウザで買い物フローを操作してください。\n終了ボタンを押すとローカルサーバーも安全に停止します。",
        style="RH.TLabel",
        justify="left",
    ).pack(anchor="w")

    button_frame = ttk.Frame(frame, style="RH.TFrame")
    button_frame.pack(anchor="w", pady=(22, 0))
    ttk.Button(
        button_frame,
        text="デモ画面を開く",
        command=lambda: webbrowser.open(runtime.demo_url),
        style="RH.TButton",
    ).pack(side="left", padx=(0, 10))
    ttk.Button(
        button_frame,
        text="診断情報",
        command=lambda: _open_file(paths.diagnostics_path),
        style="RH.TButton",
    ).pack(side="left", padx=(0, 10))

    def stop_and_close() -> None:
        root.config(cursor="watch")
        root.update_idletasks()
        runtime.stop()
        root.destroy()

    ttk.Button(
        button_frame,
        text="終了",
        command=stop_and_close,
        style="RH.TButton",
    ).pack(side="left")
    root.protocol("WM_DELETE_WINDOW", stop_and_close)
    if not no_browser:
        root.after(350, lambda: webbrowser.open(runtime.demo_url))
    root.mainloop()
    return 0


def _show_fatal_error(message: str, diagnostics_path: Path) -> None:
    logging.exception(message)
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Room Harmony 起動エラー",
            f"Room Harmonyを起動できませんでした。\n\n{message}\n\n診断情報:\n{diagnostics_path}",
        )
        root.destroy()
    except Exception:
        print(f"Room Harmony startup error: {message}", file=sys.stderr)
        print(f"Diagnostics: {diagnostics_path}", file=sys.stderr)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Room Harmony packaged demo launcher")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    paths = resolve_runtime_paths()
    _configure_logging(paths)
    validation: Optional[dict[str, Any]] = None
    runtime: Optional[RunningServer] = None
    try:
        validation = validate_resources(paths)
        _write_diagnostics(paths, validation=validation)
        if args.diagnostics:
            print(paths.diagnostics_path)
            return 0

        existing = find_existing_instance(paths.state_path)
        if existing:
            demo_url = f"{existing}{DEMO_PATH}"
            _write_diagnostics(paths, validation=validation, url=existing)
            if not args.no_browser and not args.smoke_test:
                webbrowser.open(demo_url)
            return 0

        runtime = start_server(paths, preferred_port=args.port)
        _write_diagnostics(paths, validation=validation, url=runtime.url)
        if args.smoke_test:
            smoke = run_end_to_end_smoke(runtime.url)
            _write_diagnostics(paths, validation=validation, smoke=smoke, url=runtime.url)
            print(
                f"Room Harmony smoke test passed: {runtime.demo_url} "
                f"({json.dumps(smoke, ensure_ascii=False, sort_keys=True)})"
            )
            runtime.stop()
            return 0
        if args.headless:
            if not args.no_browser:
                webbrowser.open(runtime.demo_url)
            try:
                while runtime.thread.is_alive():
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
            finally:
                runtime.stop()
            return 0
        return _run_control_window(runtime, paths, args.no_browser)
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        if runtime is not None:
            runtime.stop()
        _write_diagnostics(paths, validation=validation, error=message)
        if args.smoke_test or args.headless or args.diagnostics:
            logging.exception(message)
            print(f"Room Harmony startup error: {message}", file=sys.stderr)
            print(f"Diagnostics: {paths.diagnostics_path}", file=sys.stderr)
        else:
            _show_fatal_error(message, paths.diagnostics_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
