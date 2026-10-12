#!/usr/bin/env bash
# Builds the core as a shared library and runs the C ABI harness against it.
#
#   tools/run_abi_harness.sh [debug|release]
#
# The harness is written in C, includes include/game_core.h and dlopen()s
# libgame_core.so, so it verifies the header, the shared library and the ABI
# assumptions a platform renderer makes -- independently of the Rust tests.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROFILE="${1:-debug}"
case "$PROFILE" in
    debug)   CARGO_FLAGS=();            LIB_DIR=target/debug ;;
    release) CARGO_FLAGS=(--release);   LIB_DIR=target/release ;;
    *) echo "usage: $0 [debug|release]" >&2; exit 2 ;;
esac

command -v cc >/dev/null 2>&1 || { echo "error: a C compiler (cc) is required" >&2; exit 1; }

echo "== building libgame_core ($PROFILE) =="
cargo build -p game_core "${CARGO_FLAGS[@]}"

echo
echo "== building the C harness =="
mkdir -p tools/harness/build
cc -std=c11 -Wall -Wextra -Werror -O1 \
   -I include \
   tools/harness/harness.c \
   -o tools/harness/build/harness \
   -ldl -lm
echo "  tools/harness/build/harness"

echo
echo "== running against $LIB_DIR/libgame_core.so =="
./tools/harness/build/harness "$LIB_DIR/libgame_core.so"
