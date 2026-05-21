#!/usr/bin/env python3
"""Convenience runner for the backend hot-folder watcher.

Run from the project root as:
  python3 watch_hot_folder.py
or make executable and run:
  chmod +x watch_hot_folder.py
  ./watch_hot_folder.py

This ensures the `backend/` package is on `sys.path` then runs
`app.scripts.watch_hot_folder` as a module.
"""
from __future__ import annotations

import runpy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"

if not BACKEND.exists():
    print("Error: backend/ directory not found. Are you in the project root?")
    raise SystemExit(1)

# Ensure backend/ is importable as a package root
sys.path.insert(0, str(BACKEND))

if __name__ == "__main__":
    # Run the watcher module as __main__ so it behaves like `python -m app.scripts.watch_hot_folder`
    runpy.run_module("app.scripts.watch_hot_folder", run_name="__main__")
