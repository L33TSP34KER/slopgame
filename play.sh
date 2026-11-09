#!/usr/bin/env bash
# Emberfall — The Hollow Crown. Native desktop build.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Creating Python environment (first run)…"
  python3 -m venv .venv
  .venv/bin/pip install --quiet pygame-ce cairosvg
fi
exec .venv/bin/python -m emberfall.main "$@"
