#!/usr/bin/env bash
#
# Cross-compile the Rust core (core/) for Android and copy libgame_core.so into
# the Gradle project's jniLibs directory, where CMakeLists.txt links it from and
# AGP packages it into the APK.
#
#   ./build_core.sh                 # all three ABIs
#   ./build_core.sh arm64-v8a       # just one
#
# Requirements: a Rust toolchain with the Android targets, and the Android NDK.
#   rustup target add aarch64-linux-android armv7-linux-androideabi x86_64-linux-android
#   export ANDROID_NDK_HOME=/path/to/Android/Sdk/ndk/26.1.10909125
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

CORE_MANIFEST="${REPO_ROOT}/core/Cargo.toml"
CORE_LIB_NAME="libgame_core.so"
JNI_LIBS_DIR="${SCRIPT_DIR}/app/src/main/jniLibs"

# Android API level to link against: must be >= minSdk in app/build.gradle.kts.
API_LEVEL="${GC_ANDROID_API:-24}"

# All ABIs the APK ships, in the order they are built.
ALL_ABIS=(arm64-v8a armeabi-v7a x86_64)

die() {
    printf '\nerror: %s\n' "$*" >&2
    exit 1
}

note() {
    printf '\n=== %s\n' "$*"
}

usage() {
    cat <<EOF
usage: $(basename "$0") [ABI ...]

ABIs: ${ALL_ABIS[*]}   (default: all of them)

environment:
  ANDROID_NDK_HOME / ANDROID_NDK_ROOT / NDK_HOME   NDK to use (required)
  GC_ANDROID_API                                   API level to link (default ${API_LEVEL})
  CARGO_TARGET_DIR                                 honoured, defaults to <repo>/target

example:
  ANDROID_NDK_HOME=\$HOME/Android/Sdk/ndk/26.1.10909125 ./build_core.sh arm64-v8a
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

# ---------------------------------------------------------------------------
# arguments
# ---------------------------------------------------------------------------
if [[ $# -gt 0 ]]; then
    ABIS=("$@")
else
    ABIS=("${ALL_ABIS[@]}")
fi

for abi in "${ABIS[@]}"; do
    found=0
    for known in "${ALL_ABIS[@]}"; do
        [[ "$abi" == "$known" ]] && found=1
    done
    [[ $found -eq 1 ]] || die "unknown ABI '$abi' (expected one of: ${ALL_ABIS[*]})"
done

# ---------------------------------------------------------------------------
# toolchain checks
# ---------------------------------------------------------------------------
command -v cargo >/dev/null 2>&1 || die \
"cargo not found on PATH.  Install Rust:
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"

[[ -f "$CORE_MANIFEST" ]] || die \
"the Rust core crate is missing: ${CORE_MANIFEST} does not exist.
The core must be a cdylib named game_core, i.e. core/Cargo.toml needs:
  [lib]
  name = \"game_core\"
  crate-type = [\"cdylib\"]"

# NDK: honour the usual environment variables, then fall back to local.properties.
NDK="${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-${NDK_HOME:-}}}"
if [[ -z "$NDK" && -f "${SCRIPT_DIR}/local.properties" ]]; then
    NDK="$(sed -n 's/^ndk\.dir=//p' "${SCRIPT_DIR}/local.properties" | tail -n 1)"
fi
[[ -n "$NDK" ]] || die \
"no Android NDK found.  Set ANDROID_NDK_HOME, e.g.
  export ANDROID_NDK_HOME=\$HOME/Android/Sdk/ndk/26.1.10909125
(or put ndk.dir=... in platforms/android/local.properties)"

[[ -d "$NDK" ]] || die "ANDROID_NDK_HOME points at '${NDK}', which is not a directory"

# Host tag inside the NDK's llvm prebuilt tree.
case "$(uname -s)" in
    Linux*)   HOST_TAGS=(linux-x86_64) ;;
    Darwin*)  HOST_TAGS=(darwin-arm64 darwin-x86_64) ;;  # x86_64 builds run under Rosetta
    MINGW*|MSYS*|CYGWIN*) HOST_TAGS=(windows-x86_64) ;;
    *)        die "unsupported host: $(uname -s)" ;;
esac

TOOLCHAIN=""
for tag in "${HOST_TAGS[@]}"; do
    if [[ -d "${NDK}/toolchains/llvm/prebuilt/${tag}" ]]; then
        TOOLCHAIN="${NDK}/toolchains/llvm/prebuilt/${tag}"
        break
    fi
done
[[ -n "$TOOLCHAIN" ]] || die \
"could not find the NDK clang toolchain under
  ${NDK}/toolchains/llvm/prebuilt/{${HOST_TAGS[*]}}
Is ANDROID_NDK_HOME really an NDK (not just the SDK) directory?"

echo "ndk       = ${NDK}"
echo "     toolchain = ${TOOLCHAIN}"
echo "     api level = ${API_LEVEL}"
echo "     core      = ${CORE_MANIFEST}"

# ---------------------------------------------------------------------------
# rustup target check (fail before doing any work)
# ---------------------------------------------------------------------------
declare -A TARGET_OF_ABI=(
    [arm64-v8a]="aarch64-linux-android"
    [armeabi-v7a]="armv7-linux-androideabi"
    [x86_64]="x86_64-linux-android"
)
declare -A CC_PREFIX_OF_TARGET=(
    [aarch64-linux-android]="aarch64-linux-android"
    [armv7-linux-androideabi]="armv7a-linux-androideabi"
    [x86_64-linux-android]="x86_64-linux-android"
)

MISSING=()
if command -v rustup >/dev/null 2>&1; then
    INSTALLED_TARGETS="$(rustup target list --installed 2>/dev/null || true)"
    for abi in "${ABIS[@]}"; do
        target="${TARGET_OF_ABI[$abi]}"
        if ! grep -qx "$target" <<<"$INSTALLED_TARGETS"; then
            MISSING+=("$target")
        fi
    done
else
    echo "warning: rustup not found; assuming the Android targets are installed" >&2
fi

if [[ ${#MISSING[@]} -gt 0 ]]; then
    die "these rust targets are not installed: ${MISSING[*]}
Install them with:
  rustup target add aarch64-linux-android armv7-linux-androideabi x86_64-linux-android"
fi

# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
# 16 KB page size compatibility (Android 15+).  Set GC_MAX_PAGE_SIZE_16K=0 to
# disable, e.g. if your NDK's linker does not understand the flag.
RUSTFLAGS_EXTRA=""
if [[ "${GC_MAX_PAGE_SIZE_16K:-1}" == "1" ]]; then
    RUSTFLAGS_EXTRA="-C link-arg=-Wl,-z,max-page-size=16384 -Wl,-soname,libgame_core.so"
fi
export RUSTFLAGS="${RUSTFLAGS:-} ${RUSTFLAGS_EXTRA}"

CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-${REPO_ROOT}/target}"
export CARGO_TARGET_DIR

for abi in "${ABIS[@]}"; do
    target="${TARGET_OF_ABI[$abi]}"
    cc_prefix="${CC_PREFIX_OF_TARGET[$target]}"
    linker="${TOOLCHAIN}/bin/${cc_prefix}${API_LEVEL}-clang"
    ar="${TOOLCHAIN}/bin/llvm-ar"

    [[ -x "$linker" ]] || die "NDK linker not found or not executable: ${linker}"
    [[ -x "$ar" ]] || die "NDK llvm-ar not found: ${ar}"

    # rustc needs the linker for the target; the env var name is the uppercase
    # target triple with dashes replaced by underscores.
    env_suffix="$(tr 'a-z-' 'A-Z_' <<<"$target")"
    export "CARGO_TARGET_${env_suffix}_LINKER=${linker}"
    export "CARGO_TARGET_${env_suffix}_AR=${ar}"

    # If the repository root is a cargo *workspace* that contains core, build the
    # member by package name; otherwise core/Cargo.toml is a standalone package.
    cargo_args=(build --release --target "${target}")
    if grep -q '^\[workspace\]' "${REPO_ROOT}/Cargo.toml" 2>/dev/null; then
        cargo_args+=(--manifest-path "${REPO_ROOT}/Cargo.toml" -p game_core)
    else
        cargo_args+=(--manifest-path "${CORE_MANIFEST}")
    fi

    note "building ${abi} (${target}) with ${linker}"
    cargo "${cargo_args[@]}" || die "cargo build failed for ${target}
If the error mentions a missing linker, check GC_ANDROID_API (currently ${API_LEVEL})
and that the NDK is complete."

    built="${CARGO_TARGET_DIR}/${target}/release/${CORE_LIB_NAME}"
    [[ -f "$built" ]] || die \
"cargo reported success but ${built} does not exist.
Is the core crate a cdylib named 'game_core'?  core/Cargo.toml must contain:
  [lib]
  name = \"game_core\"
  crate-type = [\"cdylib\"]"

    dest_dir="${JNI_LIBS_DIR}/${abi}"
    mkdir -p "$dest_dir"
    cp -f "$built" "${dest_dir}/${CORE_LIB_NAME}"
    printf '  -> %s (%s)\n' \
        "${dest_dir#"${SCRIPT_DIR}/"}/${CORE_LIB_NAME}" \
        "$(du -h "${dest_dir}/${CORE_LIB_NAME}" | cut -f1)"
done

note "done"
echo "libgame_core.so installed for: ${ABIS[*]}"
echo "now build the APK:  ./gradlew assembleDebug"
