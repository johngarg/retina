from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def target_binary_name() -> str:
    system = platform.system()
    if system == "Darwin":
        return "retina-api"
    if system == "Windows":
        return "retina-api.exe"
    return "retina-api"


def main() -> None:
    api_dir = Path(__file__).resolve().parents[1]
    repo_root = api_dir.parents[1]
    tauri_backend_dir = repo_root / "apps" / "desktop" / "src-tauri" / "backend"
    build_dir = api_dir / ".pyinstaller-build"
    config_dir = api_dir / ".pyinstaller-config"
    spec_dir = api_dir / ".pyinstaller-spec"
    binary_name = target_binary_name()

    tauri_backend_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)

    binary_path = tauri_backend_dir / binary_name
    if binary_path.exists():
        binary_path.unlink()

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--name",
        "retina-api",
        "--distpath",
        str(tauri_backend_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(spec_dir),
        "--paths",
        str(api_dir),
        str(api_dir / "run_server.py"),
    ]

    environment = os.environ.copy()
    environment["PYINSTALLER_CONFIG_DIR"] = str(config_dir)

    subprocess.run(command, check=True, cwd=api_dir, env=environment)

    if not binary_path.exists():
        raise FileNotFoundError(f"Expected bundled backend executable at {binary_path}")

    if shutil.which("codesign") is None:
        print("Built sidecar without codesign availability.", file=sys.stderr)


if __name__ == "__main__":
    main()
