#!/usr/bin/env bash
# Rebuilds every generated asset and metadata table from the source art.
#
#   assets/source-sheet.svg  --(tools/extract_sprites.py)-->  assets/sprites/*.svg
#   assets/sprites/*.svg     --(tools/build_sprites.py) -->   assets/dist/*.png
#                                                             core/src/generated/sprites.rs
#   ImageMagick fonts        --(tools/build_font.py) ----->   assets/dist/font_atlas.png
#                                                             core/src/generated/font_metrics.rs
#
# assets/dist/ is the single folder every platform bundles.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for tool in rsvg-convert magick python3; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "error: '$tool' is required but was not found in PATH" >&2
        exit 1
    }
done

echo "== extracting sprites from assets/source-sheet.svg =="
python3 tools/extract_sprites.py

echo
echo "== rasterising sprites =="
python3 tools/build_sprites.py

echo
echo "== building font atlas =="
python3 tools/build_font.py

echo
echo "== assets/dist =="
ls -1 assets/dist

echo
echo "done. Bundle assets/dist/ with every platform build."
