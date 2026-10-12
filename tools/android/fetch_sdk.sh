#!/usr/bin/env bash
# Fetches the Android SDK pieces an APK build needs into .android-sdk/ inside the
# repository (gitignored).  Root `/` on this machine has very little free space,
# so nothing large goes to the default SDK location.
#
#   tools/android/fetch_sdk.sh
#
# Then build with:
#   tools/android/build_apk.sh
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
sdk="$root/.android-sdk"
dl="$root/.android-dl"
mkdir -p "$sdk/platforms" "$sdk/ndk" "$dl"
cd "$dl"

# The platform the project compiles against (see app/build.gradle.kts).
echo "== resolving the android-34 platform =="
plat=""
for n in 34_r03 34_r02 34_r01 34-ext7_r03 34-ext7_r02 33_r03; do
    url="https://dl.google.com/android/repository/platform-${n}.zip"
    code=$(curl -s -o /dev/null -w '%{http_code}' -I "$url")
    echo "   $code $url"
    if [ "$code" = "200" ]; then plat="$url"; break; fi
done
if [ -n "$plat" ]; then
    curl -sSL -o platform.zip "$plat" && unzip -q -o platform.zip -d "$sdk/platforms" \
        && echo "   platform unpacked"
else
    echo "   PLATFORM NOT FOUND -- the build cannot continue" >&2
fi

# NDK r26d is 26.1.10909125, the version the project asks for.
echo "== downloading NDK r26d (~650 MB) =="
if [ ! -d "$sdk/ndk/26.1.10909125" ]; then
    curl -sSL -o ndk.zip https://dl.google.com/android/repository/android-ndk-r26d-linux.zip \
        && unzip -q -o ndk.zip -d "$sdk/ndk" \
        && mv "$sdk/ndk/android-ndk-r26d" "$sdk/ndk/26.1.10909125" 2>/dev/null
fi
echo "== done =="
ls "$sdk/platforms" 2>/dev/null
ls "$sdk/ndk" 2>/dev/null
