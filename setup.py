#!/usr/bin/env python3
"""Bootstrap a local .venv and install dependencies for common-helpers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"

INSTALL_REQUIRES = [
    "colorama",
    "pygments",
    "requests",
]


def _venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def bootstrap() -> None:
    if not VENV_DIR.is_dir():
        print(f"Creating virtual environment at {VENV_DIR}")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])

    python = _venv_python()
    subprocess.check_call(
        [str(python), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"]
    )
    subprocess.check_call(
        [str(python), "-m", "pip", "install", *INSTALL_REQUIRES]
    )

    activate = (
        f"{VENV_DIR}\\Scripts\\activate"
        if sys.platform == "win32"
        else f"source {VENV_DIR}/bin/activate"
    )
    print(f"\nDone. Activate the environment with:\n  {activate}\n")


if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1] == "bootstrap":
        bootstrap()
        raise SystemExit(0)

setup(
    name="common-helpers",
    version="1.0.0",
    description="Personal helper scripts and utilities",
    python_requires=">=3.9",
    install_requires=INSTALL_REQUIRES,
)
