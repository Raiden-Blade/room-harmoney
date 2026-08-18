"""Build, smoke-test and archive a native Room Harmony demo release."""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DIST = ROOT / "dist"
RELEASE = ROOT / "release"
SPEC = ROOT / "packaging" / "room_harmony.spec"
FORBIDDEN_RELEASE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".env", ".log", ".pem", ".key"}


def run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def architecture_name() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine.replace(" ", "-")


def packaged_executable() -> Path:
    if sys.platform == "win32":
        return DIST / "RoomHarmony" / "RoomHarmony.exe"
    if sys.platform == "darwin":
        return DIST / "Room Harmony.app" / "Contents" / "MacOS" / "RoomHarmony"
    raise RuntimeError(f"Unsupported release platform: {sys.platform}")


def audit_bundle() -> None:
    bundle_root = DIST / ("RoomHarmony" if sys.platform == "win32" else "Room Harmony.app")
    if not bundle_root.exists():
        raise RuntimeError(f"Release bundle is missing: {bundle_root}")
    forbidden = [
        path
        for path in bundle_root.rglob("*")
        if path.is_file() and path.suffix.lower() in FORBIDDEN_RELEASE_SUFFIXES
    ]
    if forbidden:
        rendered = "\n".join(f"- {path.relative_to(bundle_root)}" for path in forbidden)
        raise RuntimeError(f"Private/runtime files leaked into the release bundle:\n{rendered}")

    data_candidates = [path.parent for path in bundle_root.rglob("products.json")]
    if len(data_candidates) != 1:
        raise RuntimeError(
            f"Expected exactly one packaged data directory, found {len(data_candidates)}"
        )
    packaged_data = data_candidates[0]
    data_files = {path.name for path in packaged_data.iterdir() if path.is_file()}
    expected = {
        "products.json",
        "qr_codes.json",
        "coordinates.json",
        "store_map.json",
        "co_purchase.json",
        "member_history.json",
        "pos_metrics.json",
        "aggregates.json",
    }
    if data_files != expected:
        raise RuntimeError(
            f"Packaged data whitelist mismatch: expected={sorted(expected)}, actual={sorted(data_files)}"
        )


def release_has_platform_trust() -> bool:
    """Return true only for an actually trusted artifact, never from an environment flag."""
    if sys.platform == "win32":
        executable = packaged_executable()
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$signature = Get-AuthenticodeSignature -LiteralPath $args[0]; "
                "if ($signature.Status -eq 'Valid') { exit 0 } else { exit 1 }",
                str(executable),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    if sys.platform == "darwin":
        app = DIST / "Room Harmony.app"
        verify = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(app)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        details = subprocess.run(
            ["codesign", "-dv", "--verbose=4", str(app)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        rendered_details = f"{details.stdout}\n{details.stderr}"
        developer_id = (
            details.returncode == 0
            and "Authority=Developer ID Application:" in rendered_details
            and "TeamIdentifier=not set" not in rendered_details
        )
        notarized = subprocess.run(
            ["xcrun", "stapler", "validate", str(app)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        return verify.returncode == 0 and developer_id and notarized.returncode == 0

    return False


def archive_release() -> Path:
    RELEASE.mkdir(parents=True, exist_ok=True)
    arch = architecture_name()
    trusted = release_has_platform_trust()
    signature_suffix = "" if trusted else "-unsigned"
    print(f"Platform trust verification: {'passed' if trusted else 'unsigned/unnotarized'}")
    if sys.platform == "win32":
        base = RELEASE / f"RoomHarmony-Windows-{arch}{signature_suffix}"
        archive = Path(shutil.make_archive(str(base), "zip", DIST, "RoomHarmony"))
    elif sys.platform == "darwin":
        archive = RELEASE / f"RoomHarmony-macOS-{arch}{signature_suffix}.zip"
        archive.unlink(missing_ok=True)
        run(
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(DIST / "Room Harmony.app"),
                str(archive),
            ]
        )
    else:
        raise RuntimeError(f"Unsupported release platform: {sys.platform}")

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Release: {archive}")
    print(f"SHA-256: {digest}")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-npm-ci", action="store_true")
    parser.add_argument("--skip-package-smoke", action="store_true")
    args = parser.parse_args()

    if sys.platform not in {"win32", "darwin"}:
        parser.error("Desktop releases are built only on Windows or macOS")

    if not args.skip_npm_ci:
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        run([npm, "ci", "--legacy-peer-deps"], cwd=FRONTEND)
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    run([npm, "run", "build"], cwd=FRONTEND)
    with tempfile.TemporaryDirectory(prefix="room-harmony-source-check-") as temp_dir:
        source_check_env = os.environ.copy()
        source_check_env["ROOM_HARMONY_APP_DATA_DIR"] = temp_dir
        run(
            [sys.executable, "backend/launcher.py", "--diagnostics"],
            cwd=ROOT,
            env=source_check_env,
        )
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC),
        ],
        cwd=ROOT,
    )

    executable = packaged_executable()
    if not executable.is_file():
        raise RuntimeError(f"Packaged executable is missing: {executable}")
    audit_bundle()

    if not args.skip_package_smoke:
        with tempfile.TemporaryDirectory(prefix="room-harmony-release-smoke-") as temp_dir:
            env = os.environ.copy()
            env["ROOM_HARMONY_APP_DATA_DIR"] = temp_dir
            run(
                [str(executable), "--smoke-test", "--no-browser"],
                cwd=ROOT,
                env=env,
            )
            diagnostics = Path(temp_dir) / "diagnostics.txt"
            if not diagnostics.is_file() or "smoke={}" in diagnostics.read_text(encoding="utf-8"):
                raise RuntimeError("Packaged smoke test did not write completion evidence")
            print(diagnostics.read_text(encoding="utf-8"), flush=True)
    archive_release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
