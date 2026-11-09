#!/usr/bin/env python3
"""Frozen entry point for the Emberfall PyInstaller artifact (mimo, dist/).

The repo root also contains main.py / agent.py from the broadcast-system demo,
which PyInstaller happily bundles as 'main' when the entry script is named the
same — hence a uniquely named launcher.

    .venv/bin/pyinstaller ... packaging/frozen_entry.py
    dist/Emberfall/Emberfall --qa --scene base --frames 200 --shot out.png
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    from emberfall.src.app import main as game_main

    game_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
