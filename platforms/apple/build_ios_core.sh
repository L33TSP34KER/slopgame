#!/usr/bin/env bash
#
# build_ios_core.sh -- cross-compile the shared game logic for iOS and lipo the
#                     simulator slices into an XCFramework.
#
# Exact cargo target names used:
#   aarch64-apple-ios         arm64 device            (iPhone/iPad)
#   aarch64-apple-ios-sim     arm64 simulator         (Apple Silicon Macs)
#   x86_64-apple-ios          x86_64 simulator        (Intel Macs)
#
# Output (all under platforms/apple/build/ios):
#   device/libgame_core.dylib                     arm64 device slice
#   simulator-arm64/libgame_core.dylib            arm64 simulator slice
#   simulator-x86_64/libgame_core.dylib           x86_64 simulator slice
#   simulator/libgame_core.dylib                  lipo -create of the two sim slices
#   SlimeArenaCore.xcframework/                   device + universal simulator
#   headers/game_core.h                           headers shipped in the XCFramework
#   current/libgame_core.dylib                    what SlimeArena.xcodeproj points at;
#                                                 refreshed per SDK by its script phase
#
# Usage:  platforms/apple/build_ios_core.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CORE_CRATE="$REPO_ROOT/core"
HEADER_SRC="$REPO_ROOT/include/game_core.h"
OUT_DIR="$SCRIPT_DIR/build/ios"

DEVICE_TARGET="aarch64-apple-ios"
SIM_ARM_TARGET="aarch64-apple-ios-sim"
SIM_X86_TARGET="x86_64-apple-ios"
ALL_TARGETS=("$DEVICE_TARGET" "$SIM_ARM_TARGET" "$SIM_X86_TARGET")

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
fail() { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Toolchain
# ---------------------------------------------------------------------------
command -v cargo >/dev/null 2>&1 || fail \
"cargo was not found in PATH. Install Rust with:
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"

command -v lipo >/dev/null 2>&1 || fail \
"lipo was not found. It ships with the Xcode Command Line Tools:
    xcode-select --install"

[ -d "$CORE_CRATE" ] || fail "the core crate directory is missing: $CORE_CRATE"
[ -f "$CORE_CRATE/Cargo.toml" ] || fail \
"$CORE_CRATE/Cargo.toml does not exist, so there is nothing to cross-compile.
The shared game logic crate must live in core/ and declare
    [lib]
    name = \"game_core\"
    crate-type = [\"cdylib\"]"

[ -f "$HEADER_SRC" ] || fail "the frozen ABI header is missing: $HEADER_SRC"

# ---------------------------------------------------------------------------
# rustup targets
# ---------------------------------------------------------------------------
if command -v rustup >/dev/null 2>&1; then
    installed="$(rustup target list --installed)"
    for target in "${ALL_TARGETS[@]}"; do
        if ! printf '%s\n' "$installed" | grep -qx "$target"; then
            info "installing rust target $target"
            rustup target add "$target"
        fi
    done
else
    warn "rustup was not found: assuming the iOS targets are already installed.
If the build fails with 'can't find crate for std', install rustup and run:
    rustup target add ${ALL_TARGETS[*]}"
fi

# ---------------------------------------------------------------------------
# Build every slice
# ---------------------------------------------------------------------------
mkdir -p "$OUT_DIR"

# Returns the built dylib path for a target, or fails with the paths it tried.
dylib_for_target() {
    local target="$1"
    local candidate
    for candidate in \
        "$CORE_CRATE/target/$target/release/libgame_core.dylib" \
        "$REPO_ROOT/target/$target/release/libgame_core.dylib"
    do
        if [ -f "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

for target in "${ALL_TARGETS[@]}"; do
    info "cargo build --release --target $target"
    (
        cd "$CORE_CRATE"
        cargo build --release --manifest-path "$CORE_CRATE/Cargo.toml" --target "$target"
    )
done

DEVICE_DYLIB="$(dylib_for_target "$DEVICE_TARGET")" || fail \
"libgame_core.dylib was not produced for $DEVICE_TARGET."
SIM_ARM_DYLIB="$(dylib_for_target "$SIM_ARM_TARGET")" || fail \
"libgame_core.dylib was not produced for $SIM_ARM_TARGET."
SIM_X86_DYLIB="$(dylib_for_target "$SIM_X86_TARGET")" || fail \
"libgame_core.dylib was not produced for $SIM_X86_TARGET."

# ---------------------------------------------------------------------------
# Stage the slices
# ---------------------------------------------------------------------------
rm -rf "$OUT_DIR/device" "$OUT_DIR/simulator" "$OUT_DIR/simulator-arm64" \
       "$OUT_DIR/simulator-x86_64" "$OUT_DIR/headers" "$OUT_DIR/SlimeArenaCore.xcframework"
mkdir -p "$OUT_DIR/device" "$OUT_DIR/simulator-arm64" "$OUT_DIR/simulator-x86_64" \
         "$OUT_DIR/simulator" "$OUT_DIR/headers" "$OUT_DIR/current"

cp "$DEVICE_DYLIB"  "$OUT_DIR/device/libgame_core.dylib"
cp "$SIM_ARM_DYLIB" "$OUT_DIR/simulator-arm64/libgame_core.dylib"
cp "$SIM_X86_DYLIB" "$OUT_DIR/simulator-x86_64/libgame_core.dylib"
cp "$HEADER_SRC"    "$OUT_DIR/headers/game_core.h"

info "lipo -create the simulator slices (arm64 + x86_64)"
lipo -create \
    "$OUT_DIR/simulator-arm64/libgame_core.dylib" \
    "$OUT_DIR/simulator-x86_64/libgame_core.dylib" \
    -output "$OUT_DIR/simulator/libgame_core.dylib"
lipo -info "$OUT_DIR/simulator/libgame_core.dylib"

# ---------------------------------------------------------------------------
# Install name: every slice must advertise @rpath/libgame_core.dylib, because
# that is the name the app links against and the name it embeds under
# SlimeArena.app/Frameworks.  A cargo-built dylib otherwise tends to carry an
# absolute build path, which does not exist on the device.
# Xcode re-signs the embedded copy ("Code Sign On Copy"), which is required after
# editing the Mach-O header.
# ---------------------------------------------------------------------------
if command -v install_name_tool >/dev/null 2>&1; then
    for slice in \
        "$OUT_DIR/device/libgame_core.dylib" \
        "$OUT_DIR/simulator-arm64/libgame_core.dylib" \
        "$OUT_DIR/simulator-x86_64/libgame_core.dylib" \
        "$OUT_DIR/simulator/libgame_core.dylib"
    do
        install_name_tool -id "@rpath/libgame_core.dylib" "$slice" \
            || warn "could not set the install name on $slice"
    done
    info "install name: @rpath/libgame_core.dylib"
else
    warn "install_name_tool not found; the embedded dylib may keep an absolute
install name, in which case the app will not launch on device."
fi

# The Xcode project references build/ios/current/libgame_core.dylib; seed it with
# the device slice so the path exists as soon as this script has run.  The
# project's script phase overwrites it with the slice matching the SDK in use.
cp "$DEVICE_DYLIB" "$OUT_DIR/current/libgame_core.dylib"

# ---------------------------------------------------------------------------
# XCFramework
# ---------------------------------------------------------------------------
if command -v xcodebuild >/dev/null 2>&1; then
    info "xcodebuild -create-xcframework"
    xcodebuild -create-xcframework \
        -library "$OUT_DIR/device/libgame_core.dylib" \
        -headers "$OUT_DIR/headers" \
        -library "$OUT_DIR/simulator/libgame_core.dylib" \
        -headers "$OUT_DIR/headers" \
        -output "$OUT_DIR/SlimeArenaCore.xcframework"
else
    warn "xcodebuild not found: skipping XCFramework creation. The per-slice
dylibs above are still usable, and SlimeArena.xcodeproj only needs
build/ios/current/libgame_core.dylib."
fi

info "done"

cat <<EOF

Device slice:      $OUT_DIR/device/libgame_core.dylib
Simulator slice:   $OUT_DIR/simulator/libgame_core.dylib  (arm64 + x86_64)
XCFramework:       $OUT_DIR/SlimeArenaCore.xcframework
Xcode link path:   $OUT_DIR/current/libgame_core.dylib

Next: open $SCRIPT_DIR/SlimeArena.xcodeproj, pick the SlimeArena scheme and a
simulator, then Run (⌘R). The target's "Select core slice" script phase copies
the slice that matches the SDK you are building for.
EOF
