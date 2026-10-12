#!/usr/bin/env bash
#
# Host-only self-tests for app/src/main/cpp/game_jni.c.
#
# These do NOT build the Android app: the real JNI wrapper is compiled for the
# host against stub <jni.h> / <android/log.h> headers and linked twice:
#
#   test_pack       -- against a fake core: the wrapper's own contract
#                      (strides, slot order, clamping, null handles, save retry)
#   test_real_core  -- against the REAL core, built here with rustc from
#                      ../../core/src/lib.rs: 900 simulated frames, every emitted
#                      command/event validated, save/load round-tripped
#
# Requires: a C11 compiler and rustc.  No NDK, no SDK, no Gradle, no network.
#
# This is the only part of the Android platform that has actually been executed
# (see ../README.md, "VERIFICATION STATUS").
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${HERE}/../../.." && pwd)"
WRAPPER="${HERE}/../app/src/main/cpp/game_jni.c"
CC="${CC:-cc}"
BUILD="${HERE}/build"

CFLAGS=(-std=c11 -Wall -Wextra -Werror -O1
        -I "${HERE}" -I "${HERE}/android" -I "${REPO_ROOT}/include")

mkdir -p "${BUILD}"

echo "== [1/2] wrapper vs. a fake core"
"${CC}" "${CFLAGS[@]}" \
    "${WRAPPER}" "${HERE}/fake_jni.c" "${HERE}/test_pack.c" \
    -o "${BUILD}/test_pack"
"${BUILD}/test_pack"

if ! command -v rustc >/dev/null 2>&1; then
    echo
    echo "!! rustc not found: skipping the real-core integration test."
    echo "!! Install Rust to run it; the fake-core test above still validates the ABI."
    exit 0
fi

echo
echo "== [2/2] wrapper vs. the real core (rustc build of core/src/lib.rs)"
# Build the real core as a host cdylib.  The output stays inside host-selfcheck/
# so nothing outside platforms/android/ is touched (and no Cargo.lock is created).
rustc --edition 2021 --crate-type cdylib -C opt-level=2 \
    -o "${BUILD}/libgame_core.so" \
    "${REPO_ROOT}/core/src/lib.rs" 2>/dev/null

"${CC}" "${CFLAGS[@]}" \
    -Wl,-rpath,"${BUILD}" -L "${BUILD}" \
    "${WRAPPER}" "${HERE}/fake_jni.c" "${HERE}/test_real_core.c" \
    -lgame_core -lm -o "${BUILD}/test_real_core"
"${BUILD}/test_real_core"
