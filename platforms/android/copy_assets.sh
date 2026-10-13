#!/usr/bin/env bash
#
# Copy the art into the APK.
#
# Android has no filesystem access to the repository at runtime, so every PNG the
# core asks for must be baked into app/src/main/assets/ before Gradle runs.  The
# file names are not invented here: they are exactly what the core reports through
# gc_sprite_file(i) and gc_font_atlas() (verified against core/src/sprite.rs:
# player.png, enemy_a.png, enemy_b.png, gun.png, bow.png, sword.png, money.png,
# xp.png, charger.png, spitter.png, miser.png + font_atlas.png).
#
#   ./copy_assets.sh
#
# Sources, in order of preference:
#   1. <repo>/assets/dist/*.png       (the canonical rasterised output)
#   2. <repo>/assets/sprites/*.png    (fallback: the per-sprite PNGs that exist today)
#
# The versioned PNGs are gitignored inside app/src/main/assets/ -- re-run this
# script (or the Gradle task below) after changing the art.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
DEST_DIR="${SCRIPT_DIR}/app/src/main/assets"

DIST_DIR="${REPO_ROOT}/assets/dist"
SPRITES_DIR="${REPO_ROOT}/assets/sprites"

# Must match core/src/sprite.rs (and GC_SPR_COUNT order in include/game_core.h).
SPRITE_FILES=(
    player.png
    enemy_a.png
    enemy_b.png
    gun.png
    bow.png
    sword.png
    money.png
    xp.png
    charger.png
    spitter.png
    miser.png
)

# Must match core/src/sprite.rs::FONT_ATLAS_FILE.
FONT_ATLAS="${GC_FONT_ATLAS:-font_atlas.png}"

die() { printf '\nerror: %s\n' "$*" >&2; exit 1; }

# ---- pick a source directory ----------------------------------------------
SRC_DIR=""
if [[ -d "$DIST_DIR" ]] && compgen -G "${DIST_DIR}/*.png" >/dev/null; then
    SRC_DIR="$DIST_DIR"
elif [[ -d "$SPRITES_DIR" ]] && compgen -G "${SPRITES_DIR}/*.png" >/dev/null; then
    SRC_DIR="$SPRITES_DIR"
    printf 'note: %s has no PNGs (or does not exist); falling back to %s\n' \
        "${DIST_DIR#"${REPO_ROOT}/"}" "${SPRITES_DIR#"${REPO_ROOT}/"}"
else
    die "no PNGs found in either
  ${DIST_DIR}
  ${SPRITES_DIR}
Rasterise the art first (tools/extract_sprites.py produces the SVGs, an SVG->PNG
step must produce assets/dist/*.png)."
fi

# ---- copy ------------------------------------------------------------------
mkdir -p "$DEST_DIR"
rm -f "${DEST_DIR}"/*.png 2>/dev/null || true

copied=0
for name in "${SPRITE_FILES[@]}"; do
    if [[ -f "${SRC_DIR}/${name}" ]]; then
        cp -f "${SRC_DIR}/${name}" "${DEST_DIR}/${name}"
        copied=$((copied + 1))
    else
        printf 'warning: missing sprite %s in %s\n' "$name" "${SRC_DIR#"${REPO_ROOT}/"}" >&2
    fi
done

if [[ -f "${SRC_DIR}/${FONT_ATLAS}" ]]; then
    cp -f "${SRC_DIR}/${FONT_ATLAS}" "${DEST_DIR}/${FONT_ATLAS}"
    copied=$((copied + 1))
else
    printf 'warning: font atlas %s not found in %s\n' \
        "$FONT_ATLAS" "${SRC_DIR#"${REPO_ROOT}/"}" >&2
    printf '         the core will still emit GC_CMD_GLYPH commands; without the atlas\n' >&2
    printf '         TextureStore falls back to the white texture (glyphs become blocks).\n' >&2
fi

[[ $copied -gt 0 ]] || die "nothing was copied from ${SRC_DIR}"

printf 'copied %d file(s) from %s ->\n  %s\n' \
    "$copied" "${SRC_DIR#"${REPO_ROOT}/"}" "${DEST_DIR#"${REPO_ROOT}/"}"

# Everything that ends up in assets/ must be accounted for, otherwise a stale PNG
# from an earlier run silently ships.
shopt -s nullglob
for path in "${DEST_DIR}"/*.png; do
    base="$(basename "$path")"
    known=0
    for name in "${SPRITE_FILES[@]}"; do
        [[ "$base" == "$name" ]] && known=1
    done
    [[ "$base" == "$FONT_ATLAS" ]] && known=1
    [[ $known -eq 1 ]] || printf 'note: extra asset also packaged: %s\n' "$base"
done
shopt -u nullglob

echo
echo "app/src/main/assets/ now contains:"
ls -1 "${DEST_DIR}" | sed 's/^/  /'
