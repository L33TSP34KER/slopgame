#!/usr/bin/env bash
#
# Host-only check of app/src/main/cpp/CMakeLists.txt.
#
# It cannot use the Android toolchain (no NDK here), so it configures the *real*
# CMakeLists.txt with the host compiler under a throwaway ABI name
# ("host-check"), which exercises:
#
#   * that the file parses at all (CMake syntax, target properties, options),
#   * the <repo>/include path computation and the game_core.h existence guard,
#   * the prebuilt-core guard: the first configure is expected to FAIL with the
#     "run build_core.sh" message, because jniLibs/host-check/libgame_core.so is
#     deliberately absent at that point,
#   * the imported-library wiring and the -Wl,-z,max-page-size=16384 link option,
#   * a real compile+link of game_jni.c with -Wall -Wextra (using the stub jni.h
#     from this directory, because there is no NDK jni.h on the host),
#   * that the resulting .so exports every Java_com_gamecore_NativeCore_* symbol.
#
# Nothing here is used by Gradle: the temp ABI directory is removed again, and
# the host build of the core is only borrowed from ./build (see run.sh).
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$(cd -- "${HERE}/.." && pwd)"
CPP_DIR="${ANDROID_DIR}/app/src/main/cpp"
REPO_ROOT="$(cd -- "${ANDROID_DIR}/../.." && pwd)"
BUILD="${HERE}/build"
CMAKE_BUILD="${HERE}/cmake-build"
ABI="host-check"                      # never one of the Gradle abiFilters
JNI_ABI_DIR="${ANDROID_DIR}/app/src/main/jniLibs/${ABI}"
CC="${CC:-cc}"

command -v cmake >/dev/null 2>&1 || { echo "cmake not found; skipping"; exit 0; }

mkdir -p "${BUILD}" "${CMAKE_BUILD}"

# ---- 1. the real core, built for the host (reuse run.sh's work) ------------
if [[ ! -f "${BUILD}/libgame_core.so" ]]; then
    echo "== building the core for the host (rustc)"
    rustc --edition 2021 --crate-type cdylib -C opt-level=2 \
        -o "${BUILD}/libgame_core.so" "${REPO_ROOT}/core/src/lib.rs" 2>/dev/null
fi

# ---- 2. a stub liblog, because find_library(log) does not exist on Linux ----
cat > "${BUILD}/log_stub.c" <<'EOF'
/* Host stub for the one liblog symbol game_jni.c uses. */
int __android_log_print(int prio, const char *tag, const char *fmt, ...)
{
    (void)prio; (void)tag; (void)fmt;
    return 0;
}
EOF
"${CC}" -c -O1 -o "${BUILD}/log_stub.o" "${BUILD}/log_stub.c"
ar rcs "${BUILD}/liblogstub.a" "${BUILD}/log_stub.o"

# ---- 3. phase one: the missing-core guard must fire ------------------------
rm -rf "${CMAKE_BUILD}" "${JNI_ABI_DIR}"
mkdir -p "${CMAKE_BUILD}"

echo
echo "== phase 1: expect a FATAL_ERROR because no prebuilt core exists yet"
set +e
OUTPUT="$(cmake -S "${CPP_DIR}" -B "${CMAKE_BUILD}" \
    -DANDROID_ABI="${ABI}" -Dgc_log_lib="${BUILD}/liblogstub.a" 2>&1)"
STATUS=$?
set -e
if [[ $STATUS -eq 0 ]]; then
    echo "!! configure unexpectedly succeeded without a prebuilt core" >&2
    exit 1
fi
if ! grep -q "Prebuilt core missing" <<<"$OUTPUT"; then
    echo "!! configure failed, but not with the intended message:" >&2
    echo "$OUTPUT" >&2
    exit 1
fi
echo "   guard fired as intended:"
grep -A2 "Prebuilt core missing" <<<"$OUTPUT" | sed 's/^/   /'

# ---- 4. phase two: with the core in place, configure for real --------------
mkdir -p "${JNI_ABI_DIR}"
cp -f "${BUILD}/libgame_core.so" "${JNI_ABI_DIR}/libgame_core.so"

echo
echo "== phase 2: configure with ${ABI}/libgame_core.so present"
rm -rf "${CMAKE_BUILD}"
# The stub jni.h lives in this directory; there is no NDK jni.h on the host.
cmake -S "${CPP_DIR}" -B "${CMAKE_BUILD}" \
    -DANDROID_ABI="${ABI}" \
    -Dgc_log_lib="${BUILD}/liblogstub.a" \
    -DCMAKE_C_FLAGS="-I${HERE} -I${HERE}/android" \
    > "${BUILD}/cmake-configure.log" 2>&1 || {
        echo "!! configure failed:" >&2; cat "${BUILD}/cmake-configure.log" >&2; exit 1; }

echo "== building libgame_jni.so with the host compiler"
cmake --build "${CMAKE_BUILD}" -j 2 > "${BUILD}/cmake-build.log" 2>&1 || {
    echo "!! build failed:" >&2; cat "${BUILD}/cmake-build.log" >&2; exit 1; }

if grep -qE "warning:" "${BUILD}/cmake-build.log"; then
    echo "!! compiler warnings while building game_jni.c:" >&2
    grep -E "warning:" "${BUILD}/cmake-build.log" >&2
    exit 1
fi

JNI_SO="$(find "${CMAKE_BUILD}" -name 'libgame_jni.so' -print -quit)"
[[ -n "${JNI_SO}" ]] || { echo "!! libgame_jni.so was not produced" >&2; exit 1; }

# ---- 5. every JNI entry point must be exported -----------------------------
EXPECTED=$(grep -c '^Java_com_gamecore_NativeCore_' "${CPP_DIR}/game_jni.c")
FOUND=$(nm -D --defined-only "${JNI_SO}" | grep -c ' T Java_com_gamecore_NativeCore_' || true)
echo
echo "libgame_jni.so: ${FOUND} exported JNI symbols (expected ${EXPECTED})"
nm -D --defined-only "${JNI_SO}" | grep ' T Java_com_gamecore_NativeCore_' | awk '{print "   " $3}'

# The temp ABI directory must not survive: it holds a host .so and would be
# packaged by Gradle if it were left behind.
rm -rf "${JNI_ABI_DIR}"

if [[ "${FOUND}" -ne "${EXPECTED}" ]]; then
    echo "!! symbol count mismatch" >&2
    exit 1
fi

echo
echo "CMakeLists.txt + game_jni.c: CONFIGURE, COMPILE AND LINK ALL SUCCEEDED (host toolchain)"
