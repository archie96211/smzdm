#!/usr/bin/env python3
"""Build the Windows onedir EXE with one Python command."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe" if os.name == "nt" else VENV_DIR / "bin" / "python"
DIST_EXE = ROOT / "dist" / "smzdm_monitor" / "smzdm_monitor.exe"
WECHAT_BRIDGE_EXE = ROOT / "wechat_bridge" / "smzdm_wechat_bridge.exe"


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    print(f"\n> {' '.join(command)}")
    subprocess.run(command, cwd=str(cwd), check=True)


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def ensure_venv() -> None:
    if VENV_PYTHON.exists():
        return
    run([sys.executable, "-m", "venv", str(VENV_DIR)])


def npm_command() -> str:
    if os.name == "nt" and command_exists("npm.cmd"):
        return "npm.cmd"
    return "npm"


def build_wechat_bridge() -> None:
    if not command_exists("go"):
        raise SystemExit("Go was not found in PATH. Install Go 1.25+ before building the bundled WeChat bridge.")

    env = os.environ.copy()
    env.setdefault("GOTOOLCHAIN", "go1.25.0")
    run(["go", "mod", "tidy"], cwd=ROOT / "wechat_bridge")
    print(f"\n> go build -o {WECHAT_BRIDGE_EXE} .")
    subprocess.run(
        ["go", "build", "-o", str(WECHAT_BRIDGE_EXE), "."],
        cwd=str(ROOT / "wechat_bridge"),
        env=env,
        check=True,
    )


def build(args: argparse.Namespace) -> None:
    ensure_venv()

    if not args.skip_python_deps:
        run([
            str(VENV_PYTHON),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            "requirements.txt",
            "pyinstaller",
        ])

    if not args.skip_frontend:
        npm = npm_command()
        if not args.skip_npm_install:
            run([npm, "install"])
        run([npm, "run", "build"])

    if not args.skip_wechat_bridge:
        build_wechat_bridge()

    if not args.skip_icon:
        run([str(VENV_PYTHON), str(ROOT / "scripts" / "create_icon.py")])

    pyinstaller_command = [
        str(VENV_PYTHON),
        "-m",
        "PyInstaller",
        str(ROOT / "scripts" / "smzdm_monitor.spec"),
        "--noconfirm",
    ]
    if args.clean:
        pyinstaller_command.append("--clean")
    run(pyinstaller_command)

    if not DIST_EXE.exists():
        raise SystemExit(f"Build finished but EXE was not found: {DIST_EXE}")
    print(f"\nBuild complete: {DIST_EXE}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build dist/smzdm_monitor/smzdm_monitor.exe")
    parser.add_argument("--no-clean", dest="clean", action="store_false", help="Do not pass --clean to PyInstaller")
    parser.add_argument("--skip-python-deps", action="store_true", help="Do not install Python dependencies")
    parser.add_argument("--skip-npm-install", action="store_true", help="Do not run npm install")
    parser.add_argument("--skip-frontend", action="store_true", help="Do not rebuild the React frontend")
    parser.add_argument("--skip-icon", action="store_true", help="Do not regenerate assets/icon.ico")
    parser.add_argument("--skip-wechat-bridge", action="store_true", help="Do not rebuild the Go WeChat bridge")
    parser.set_defaults(clean=True)
    return parser.parse_args()


if __name__ == "__main__":
    build(parse_args())
