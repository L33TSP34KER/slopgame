#!/usr/bin/env bash
#
# build_macos.sh -- build the Rust core and the macOS app, and assemble a real
#                  SlimeArena.app bundle.
#
# Steps:
#   1. sanity-check the toolchain (cargo, swift) and the assets
#   2. refresh the vendored copy of include/game_core.h and check that the ABI
#      version in the header matches the one hard-coded in GameCore.swift
#   3. cargo build --release in core/            -> libgame_core.dylib
#   4. swift build -c release                    -> SlimeArenaMac
#   5. assemble platforms/apple/build/SlimeArena.app:
#         Contents/MacOS/SlimeArenaMac
#         Contents/Frameworks/libgame_core.dylib   (install_name @rpath/...)
#         Contents/Resources/Assets/*.png
#         Contents/Info.plist
#      and re-sign it ad-hoc (install_name_tool invalidates the signature on
#      Apple Silicon, and an invalid signature will not launch).
#
# Usage:  platforms/apple/build_macos.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APP_OUT_DIR="$SCRIPT_DIR/build"
APP_BUNDLE="$APP_OUT_DIR/SlimeArena.app"
CONTENTS="$APP_BUNDLE/Contents"

CORE_CRATE="$REPO_ROOT/core"
HEADER_SRC="$REPO_ROOT/include/game_core.h"
HEADER_DST="$SCRIPT_DIR/Sources/CGameCore/include/game_core.h"
SWIFT_ABI_FILE="$SCRIPT_DIR/Sources/SlimeArenaRenderer/GameCore.swift"
MACOS_PLIST="$SCRIPT_DIR/Packaging/macOS/Info.plist"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
fail()  { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Toolchain and inputs
# ---------------------------------------------------------------------------
command -v cargo >/dev/null 2>&1 || fail \
"cargo was not found in PATH.

Install Rust (https://rustup.rs) and re-run this script, e.g.
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
    source \"\$HOME/.cargo/env\""

command -v swift >/dev/null 2>&1 || fail \
"swift was not found in PATH.

Install Xcode (or the Command Line Tools: 'xcode-select --install') and make
sure 'swift build' works before re-running this script."

[ -f "$HEADER_SRC" ] || fail "the frozen ABI header is missing: $HEADER_SRC"
[ -f "$SWIFT_ABI_FILE" ] || fail "missing $SWIFT_ABI_FILE"
[ -f "$MACOS_PLIST" ] || fail "missing $MACOS_PLIST"

[ -d "$CORE_CRATE" ] || fail "the core crate directory is missing: $CORE_CRATE"
[ -f "$CORE_CRATE/Cargo.toml" ] || fail \
"$CORE_CRATE/Cargo.toml does not exist, so 'cargo build' cannot produce
libgame_core.dylib. The shared game logic crate must live in core/."

# Assets: assets/dist is the canonical folder produced by the asset pipeline;
# assets/sprites is the checked-in source folder used as a fallback.
ASSET_DIR=""
for candidate in "$REPO_ROOT/assets/dist" "$REPO_ROOT/assets/sprites"; do
    if [ -d "$candidate" ]; then
        shopt -s nullglob
        probe=("$candidate"/*.png)
        shopt -u nullglob
        if [ "${#probe[@]}" -gt 0 ]; then
            ASSET_DIR="$candidate"
            break
        fi
    fi
done
[ -n "$ASSET_DIR" ] || fail \
"no PNG assets found.

Looked for *.png in:
    $REPO_ROOT/assets/dist
    $REPO_ROOT/assets/sprites
Run the asset pipeline (tools/) so the sprite PNGs and the font atlas exist."

shopt -s nullglob
ASSET_PNGS=("$ASSET_DIR"/*.png)
shopt -u nullglob
info "assets:       ${#ASSET_PNGS[@]} PNG(s) from $ASSET_DIR"

# ---------------------------------------------------------------------------
# 2. Keep the vendored header in sync + ABI version check
# ---------------------------------------------------------------------------
if ! cmp -s "$HEADER_SRC" "$HEADER_DST"; then
    cp "$HEADER_SRC" "$HEADER_DST"
    info "refreshed the vendored copy of game_core.h"
fi

header_abi="$(awk '
    /^#define[ \t]+GC_ABI_VERSION/ {
        for (i = 1; i <= NF; i++) {
            if ($i ~ /^[0-9]+u?$/) { value = $i; sub(/u$/, "", value); print value; exit }
        }
    }' "$HEADER_SRC")"
swift_abi="$(awk '
    /public static let version: UInt32 =/ { print $NF; exit }' "$SWIFT_ABI_FILE")"

[ -n "$header_abi" ] || fail "could not read GC_ABI_VERSION from $HEADER_SRC"
[ -n "$swift_abi" ]  || fail "could not read GCABI.version from $SWIFT_ABI_FILE"

if [ "$header_abi" != "$swift_abi" ]; then
    fail "ABI version drift: game_core.h says GC_ABI_VERSION=$header_abi but
GameCore.swift says GCABI.version=$swift_abi.
Update Sources/SlimeArenaRenderer/GameCore.swift (and the model structs) to
match the header before building."
fi
info "core ABI:     version $header_abi (header and Swift wrapper agree)"

# ---------------------------------------------------------------------------
# 3. Build the Rust core
# ---------------------------------------------------------------------------
info "building the core: cargo build --release --manifest-path $CORE_CRATE/Cargo.toml"
(
    cd "$CORE_CRATE"
    cargo build --release --manifest-path "$CORE_CRATE/Cargo.toml"
)

DYLIB=""
for candidate in \
    "$CORE_CRATE/target/release/libgame_core.dylib" \
    "$REPO_ROOT/target/release/libgame_core.dylib"
do
    if [ -f "$candidate" ]; then
        DYLIB="$candidate"
        break
    fi
done

[ -n "$DYLIB" ] || fail \
"cargo finished but libgame_core.dylib was not produced.

Looked in:
    $CORE_CRATE/target/release/libgame_core.dylib
    $REPO_ROOT/target/release/libgame_core.dylib
Check that core/Cargo.toml declares
    [lib]
    name = \"game_core\"
    crate-type = [\"cdylib\"]"
info "core dylib:   $DYLIB"

# ---------------------------------------------------------------------------
# 4. Build the Swift executable
# ---------------------------------------------------------------------------
info "building the Swift package: swift build -c release"
swift build -c release --package-path "$SCRIPT_DIR"

BINARY=""
for candidate in \
    "$SCRIPT_DIR/.build/release/SlimeArenaMac" \
    "$SCRIPT_DIR/.build/arm64-apple-macosx/release/SlimeArenaMac" \
    "$SCRIPT_DIR/.build/x86_64-apple-macosx/release/SlimeArenaMac"
do
    if [ -x "$candidate" ]; then
        BINARY="$candidate"
        break
    fi
done
[ -n "$BINARY" ] || fail "swift build succeeded but the SlimeArenaMac executable was not found."
info "executable:   $BINARY"

# ---------------------------------------------------------------------------
# 5. Assemble SlimeArena.app
# ---------------------------------------------------------------------------
info "assembling $APP_BUNDLE"
rm -rf "$APP_BUNDLE"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Frameworks" "$CONTENTS/Resources/Assets"

cp "$BINARY" "$CONTENTS/MacOS/SlimeArenaMac"
chmod +x "$CONTENTS/MacOS/SlimeArenaMac"

cp "$DYLIB" "$CONTENTS/Frameworks/libgame_core.dylib"

# The dylib advertises itself as @rpath/libgame_core.dylib ...
install_name_tool -id "@rpath/libgame_core.dylib" "$CONTENTS/Frameworks/libgame_core.dylib"

# ... and the executable must reference that same @rpath name rather than the
# absolute build path.
old_ref="$(otool -L "$CONTENTS/MacOS/SlimeArenaMac" | awk '/libgame_core/ { print $1; exit }')"
if [ -n "$old_ref" ]; then
    install_name_tool -change "$old_ref" "@rpath/libgame_core.dylib" "$CONTENTS/MacOS/SlimeArenaMac"
    info "relinked:     $old_ref -> @rpath/libgame_core.dylib"
else
    warn "the executable does not mention libgame_core; check the linker flags in Package.swift"
fi

# The Swift target already has -rpath @loader_path/../Frameworks, but make sure.
if ! otool -l "$CONTENTS/MacOS/SlimeArenaMac" | grep -q "@loader_path/../Frameworks"; then
    install_name_tool -add_rpath "@loader_path/../Frameworks" "$CONTENTS/MacOS/SlimeArenaMac"
fi

cp "$MACOS_PLIST" "$CONTENTS/Info.plist"
cp "${ASSET_PNGS[@]}" "$CONTENTS/Resources/Assets/"

# Font atlas: the core names it at runtime via gc_font_atlas, so warn if the
# asset folder has no plausible atlas PNG instead of failing the build.
if ! ls "$CONTENTS/Resources/Assets" | grep -qi 'font\|atlas\|glyph'; then
    warn "no font/atlas PNG in Resources/Assets: text will not render until
gc_font_atlas()'s file is produced by the asset pipeline."
fi

# Ad-hoc signature: required on Apple Silicon after install_name_tool, and
# harmless elsewhere.
if command -v codesign >/dev/null 2>&1; then
    info "ad-hoc signing"
    codesign --force --sign - --timestamp=none "$CONTENTS/Frameworks/libgame_core.dylib" >/dev/null 2>&1 || \
        warn "could not sign the dylib; Gatekeeper may refuse to launch the app"
    codesign --force --sign - --timestamp=none "$APP_BUNDLE" >/dev/null 2>&1 || \
        warn "could not sign the app bundle"
    codesign --verify --deep --verbose=1 "$APP_BUNDLE" >/dev/null 2>&1 || \
        warn "codesign --verify reported a problem; try 'codesign --force --deep -s - $APP_BUNDLE'"
else
    warn "codesign not found; the bundle is unsigned"
fi

info "done"

cat <<EOF

Bundle:  $APP_BUNDLE
Run:     open "$APP_BUNDLE"
or:      "$CONTENTS/MacOS/SlimeArenaMac"

Controls: WASD / arrows move, mouse aims, left click shoots,
          space = dash, esc = pause, R = restart.
EOF
