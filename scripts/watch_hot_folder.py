#!/usr/bin/env python3
"""Convenience runner for the backend hot-folder watcher.

Run from the project root as:
  python3 watch_hot_folder.py
or make executable and run:
  chmod +x watch_hot_folder.py
  ./watch_hot_folder.py

This ensures the `backend/` package is on `sys.path`, loads `backend/.env`
into the process environment (without overwriting existing env vars), then
runs `app.scripts.watch_hot_folder` as a module.
"""
from __future__ import annotations

import os
import runpy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"

if not BACKEND.exists():
    print("Error: backend/ directory not found. Are you in the project root?")
    raise SystemExit(1)

# Load environment file from backend/.env if present (do not overwrite existing env vars)
env_path = BACKEND / ".env"
if env_path.exists():
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            # Only set if not already present in environment
            if key and key not in os.environ:
                os.environ[key] = val
        print(f"Loaded environment variables from {env_path}")
    except Exception as exc:
        print(f"Warning: failed to read {env_path}: {exc}")

# Ensure backend/ is importable as a package root
sys.path.insert(0, str(BACKEND))


if __name__ == "__main__":
    # Run the watcher module as __main__ so it behaves like `python -m app.scripts.watch_hot_folder`
    runpy.run_module("app.scripts.watch_hot_folder", run_name="__main__")
