#!/usr/bin/env bash
#
# Builds a debug APK end to end.
#
#   tools/android/build_apk.sh                 # every ABI the project ships
#   tools/android/build_apk.sh arm64-v8a       # one ABI, much faster
#
# What it does, in order:
#   1. assembles a rustc sysroot that has the Android std (rustup cannot install
#      targets when $RUSTUP_HOME is read-only, which it is in some sandboxes);
#   2. cross-compiles the Rust core to libgame_core.so for each ABI;
#   3. copies them into app/src/main/jniLibs/, where CMakeLists.txt imports them;
#   4. refreshes the art in app/src/main/assets/;
#   5. runs Gradle's assembleDebug.
#
# Everything it downloads lives under .android-sdk/ and .android-dl/ inside the
# repository, so a machine with a small root filesystem can still build.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
sdk="$root/.android-sdk"
dl="$root/.android-dl"
ndk="$sdk/ndk/26.1.10909125"
sysroot="$root/.android-rust-sysroot"
api="${GC_ANDROID_API:-24}"

# Java 21 is the newest JDK Gradle 8.7 supports.
if [ -d /usr/lib/jvm/java-21-openjdk ]; then
    export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk}"
fi

abis=("$@")
if [ "${#abis[@]}" -eq 0 ]; then
    abis=(arm64-v8a armeabi-v7a x86_64)
fi

# ABI -> rust target / NDK clang prefix
target_for() {
    case "$1" in
        arm64-v8a)   echo "aarch64-linux-android" ;;
        armeabi-v7a) echo "armv7-linux-androideabi" ;;
        x86_64)      echo "x86_64-linux-android" ;;
        *) echo "unknown ABI: $1" >&2; exit 1 ;;
    esac
}

[ -d "$ndk" ] || { echo "error: NDK missing at $ndk; run tools/android/fetch_sdk.sh" >&2; exit 1; }
[ -d "$sdk/platforms/android-34" ] || { echo "error: android-34 platform missing; run tools/android/fetch_sdk.sh" >&2; exit 1; }

# --- 1. sysroot with the Android stds --------------------------------------
toolchain="$(rustc --print sysroot)"
mkdir -p "$sysroot/lib"
for f in "$toolchain"/lib/*; do
    [ "$(basename "$f")" = rustlib ] && continue
    ln -sfn "$f" "$sysroot/lib/"
done
if [ -L "$sysroot/lib/rustlib" ] || [ ! -d "$sysroot/lib/rustlib" ]; then
    rm -f "$sysroot/lib/rustlib"
    mkdir -p "$sysroot/lib/rustlib"
    for f in "$toolchain"/lib/rustlib/*; do
        ln -sfn "$f" "$sysroot/lib/rustlib/"
    done
fi

for abi in "${abis[@]}"; do
    rt="$(target_for "$abi")"
    if [ ! -d "$sysroot/lib/rustlib/$rt/lib" ]; then
        tar="$dl/rust-std-$rt.tar.gz"
        [ -f "$tar" ] || curl -sSL -o "$tar" \
            "https://static.rust-lang.org/dist/rust-std-$(rustc -V | cut -d' ' -f2)-$rt.tar.gz"
        ver="$(rustc -V | cut -d' ' -f2)"
        rm -rf "$dl/rust-std-$ver-$rt"
        tar xzf "$tar" -C "$dl"
        # The tarball unpacks to <ver>-<target>/rust-std-<target>/lib/rustlib/...
        src="$dl/rust-std-$ver-$rt/rust-std-$rt/lib/rustlib/$rt"
        [ -d "$src" ] || { echo "error: unexpected std layout under $dl" >&2; exit 1; }
        rm -f "$sysroot/lib/rustlib/$rt"
        cp -r "$src" "$sysroot/lib/rustlib/"
        echo "=== std for $rt installed into the local sysroot"
    fi
done

# --- 2. the core, one ABI at a time ---------------------------------------
for abi in "${abis[@]}"; do
    rt="$(target_for "$abi")"
    # The NDK spells 32-bit ARM's wrapper "armv7a-...", not "armv7-...".
    prefix="$rt"
    [ "$rt" = "armv7-linux-androideabi" ] && prefix="armv7a-linux-androideabi"
    clang="$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/$prefix$api-clang"
    [ -x "$clang" ] || { echo "error: no NDK clang at $clang" >&2; exit 1; }
    echo "=== building libgame_core.so for $abi ($rt)"
    env \
        CARGO_TARGET_DIR="$root/target" \
        "CARGO_TARGET_$(echo "$rt" | tr 'a-z-' 'A-Z_')_LINKER=$clang" \
        RUSTFLAGS="--sysroot=$sysroot -C link-arg=-Wl,-z,max-page-size=16384 -C link-arg=-Wl,-soname,libgame_core.so" \
        cargo build --release --target "$rt" -p game_core --manifest-path "$root/core/Cargo.toml"
    dest="$root/platforms/android/app/src/main/jniLibs/$abi"
    mkdir -p "$dest"
    cp "$root/target/$rt/release/libgame_core.so" "$dest/libgame_core.so"
    ls -la "$dest/libgame_core.so"
done

# --- 3. art, then the APK -------------------------------------------------
bash "$root/platforms/android/copy_assets.sh" 2>/dev/null || echo "note: copy_assets.sh skipped"

export ANDROID_HOME="$sdk"
export ANDROID_SDK_ROOT="$sdk"
export ANDROID_NDK_HOME="$ndk"
export GRADLE_USER_HOME="$root/.gradle-home"
# Android's own user directory (analytics, adb keys, caches) defaults to
# ~/.android, which is not writable here.  AGP refuses to start when the several
# ways of naming that folder disagree, so they are all pointed at one path.
# Android wants to write to ~/.android and ~/.config, neither of which is
# writable here, so the build gets a home of its own inside the repository.
# $HOME/.android, $XDG_CONFIG_HOME/.android and $ANDROID_USER_HOME all resolve
# to the same directory.
export ANDROID_FAKE_HOME="$root/.android-home"
export HOME="$ANDROID_FAKE_HOME"
export XDG_CONFIG_HOME="$ANDROID_FAKE_HOME"
export XDG_CACHE_HOME="$ANDROID_FAKE_HOME/cache"
export XDG_DATA_HOME="$ANDROID_FAKE_HOME/share"
# AGP refuses to start when *more than one* of these is set, even if they agree
# (it compares the raw values), so only the recommended one is exported.
export ANDROID_USER_HOME="$ANDROID_FAKE_HOME/.android"
unset ANDROID_SDK_HOME ANDROID_PREFS_ROOT 2>/dev/null || true
mkdir -p "$ANDROID_USER_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
# Java reads user.home from the passwd entry, not from $HOME, so the JVM has to
# be told as well or AGP sees /home/<user>/.android disagreeing with everything
# else.  GRADLE_OPTS covers the forked daemon, -D covers the launcher.
export GRADLE_OPTS="-Duser.home=$ANDROID_FAKE_HOME"

# Prefer the project's wrapper; otherwise fetch the distribution it pins (the
# repository ships gradle-wrapper.properties but no wrapper script or jar).
# Build-tools: reuse the one already on the system rather than downloading
# another (AGP asks for the version pinned below).
mkdir -p "$sdk/build-tools" "$sdk/licenses"
if [ ! -e "$sdk/build-tools/36.1.0" ] && [ -d /opt/android-sdk/build-tools/36.1.0 ]; then
    ln -sfn /opt/android-sdk/build-tools/36.1.0 "$sdk/build-tools/36.1.0"
fi
# The standard SDK licence hashes, so AGP stops asking for them.
if [ ! -f "$sdk/licenses/android-sdk-license" ]; then
    printf '\n24333f8a63b6825ea9c5514f83c2829b004d1fee\n84831b9409646a918e30573bab4c9c91346d8abd\n' \
        > "$sdk/licenses/android-sdk-license"
fi

gradle_bin=""
if [ -x "$root/platforms/android/gradlew" ]; then
    gradle_bin="$root/platforms/android/gradlew"
else
    ver="$(grep -o 'gradle-[0-9.]*-bin' "$root/platforms/android/gradle/wrapper/gradle-wrapper.properties" \
            | head -1 | sed 's/gradle-//; s/-bin//')"
    ver="${ver:-8.7}"
    dist="$root/.gradle-dist/gradle-$ver"
    if [ ! -x "$dist/bin/gradle" ]; then
        zip="$dl/gradle-$ver-bin.zip"
        [ -f "$zip" ] || curl -sSL -o "$zip" "https://services.gradle.org/distributions/gradle-$ver-bin.zip"
        mkdir -p "$root/.gradle-dist"
        unzip -q -o "$zip" -d "$root/.gradle-dist"
    fi
    gradle_bin="$dist/bin/gradle"
fi

cd "$root/platforms/android"
echo "=== gradle assembleDebug (abis: ${abis[*]}) via $gradle_bin"
"$gradle_bin" --no-daemon --console=plain \
    -Duser.home="$ANDROID_FAKE_HOME" \
    -Pabis="$(IFS=,; echo "${abis[*]}")" assembleDebug

apk="$root/platforms/android/app/build/outputs/apk/debug/app-debug.apk"
if [ -f "$apk" ]; then
    echo
    echo "=== APK built: $apk"
    ls -la "$apk"
    unzip -l "$apk" | grep -E "lib/|classes" | head -10
else
    echo "error: gradle finished but no APK at $apk" >&2
    exit 1
fi
