#!/usr/bin/env python3
"""Build the WeChat bridge EXE with one Python command."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BRIDGE_DIR = ROOT / "wechat_bridge"
BRIDGE_EXE = BRIDGE_DIR / "smzdm_wechat_bridge.exe"


def run(command: list[str], *, cwd: Path = BRIDGE_DIR, env: dict[str, str] | None = None) -> None:
    print(f"\n> {' '.join(command)}")
    subprocess.run(command, cwd=str(cwd), env=env, check=True)


def main() -> None:
    if shutil.which("go") is None:
        raise SystemExit("Go was not found in PATH. Install Go 1.25+ before building the WeChat bridge.")

    env = os.environ.copy()
    env.setdefault("GOTOOLCHAIN", "go1.25.0")

    run(["go", "mod", "tidy"], env=env)
    run(["go", "build", "-o", str(BRIDGE_EXE), "."], env=env)

    if not BRIDGE_EXE.exists():
        raise SystemExit(f"Build finished but EXE was not found: {BRIDGE_EXE}")
    print(f"\nBuild complete: {BRIDGE_EXE}")


if __name__ == "__main__":
    main()
