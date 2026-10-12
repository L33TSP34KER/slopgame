# host-selfcheck — the parts of this platform that have actually been run

These files are **not** part of the Android build (Gradle never sees them).  They
exist so the two riskiest pieces — the JNI seam and the native build — could be
reviewed *by running them* on a Linux host that has no Android SDK, no NDK, no
Gradle and no JNI headers.

```bash
./run.sh          # C11 compiler + rustc:   the JNI wrapper, against a fake core AND the real core
./cmake_check.sh  # cmake + C11 compiler:   configures/builds the real CMakeLists.txt for the host
```

`CC=gcc ./run.sh` picks a different compiler.

## Files

| file | purpose |
| --- | --- |
| `jni.h`, `android/log.h` | minimal **stub** headers for host compilation only.  Not the NDK headers; never put this directory on an Android include path. |
| `fake_jni.h`, `fake_jni.c` | a fake `JNIEnv` whose arrays are plain C structs, so the `GetPrimitiveArrayCritical`/`GetByteArrayElements` paths can run without a JVM. |
| `test_pack.c` | fake core + ~40 assertions about the wrapper itself. |
| `test_real_core.c` | the real core (built by `run.sh` with `rustc`) driven through the JNI entry points for 900 frames. |
| `run.sh` | builds and runs both of the above. |
| `cmake_check.sh` | two-phase CMake check (the missing-core guard must fire, then a real configure+compile+link). |
| `build/`, `cmake-build/` | generated, gitignored. |

## What `run.sh` proves

* `sizeof`/`offsetof` of `gc_cmd`, `gc_event`, `gc_status`, `gc_input` match the
  documented byte layout (the file-scope `GC_ASSERT_LAYOUT`s must compile), and
  they agree with the Rust core's own `size_of`/offset unit tests.
* the command SoA packing (9 floats + 4 ints per command) and event packing
  (3 floats + 1 int), including the exact slot of every field;
* clamping to `count`, to the float array and to the int array independently;
* `nativeUpdate` forwards `gc_input` field-for-field, in order;
* `nativeStatus` field order (7 ints / 3 floats) and its refusal to write into
  arrays that are too small;
* the grow-and-retry save contract (`-1` when the blob does not fit, byte count
  otherwise), and that a **corrupt** blob is rejected;
* against the real core, over 900 frames (≈15 s of gameplay):

  ```
  136820 commands total, 427 in the busiest frame, 60 events
  kinds seen: sprite=1 rect=1 glyph=1 (shadow=1 flash=1), rotated cmds=10638
  distinct sprite ids used: 7/8, highest event type: 14
  ```

  with every command checked for a known kind, a valid sprite id, finite geometry,
  non-negative size, a valid glyph UV rect and no unknown flag bits; every event
  for a type in 1..14 with a finite payload; the status snapshot for an in-range
  state and hp within `[0, max]`; and the view scale against `fbHeight / 720`.

### Finding: `GC_CMD_SPRITE` carries no UV rect

In all 136 820 commands the core emitted, sprite commands had
`u0 = v0 = u1 = v1 = 0` (the header documents `u0..v1` as the *glyph* atlas rect
only).  A renderer that forwarded those UVs would sample a single texel and draw
every sprite as a flat colour.  `GameRenderer` therefore substitutes
`(0,0)-(1,1)` for sprites and rects, and `test_real_core.c` asserts that the core
never starts carrying sprite UVs, so a semantics change fails the test instead of
silently breaking sprites.

## What `cmake_check.sh` proves

* `app/src/main/cpp/CMakeLists.txt` parses and the `<repo>/include` path
  computation lands on the real `game_core.h`;
* the "Prebuilt core missing — run build_core.sh" guard fires when
  `jniLibs/<abi>/libgame_core.so` is absent (phase 1);
* with the library present it configures, compiles `game_jni.c` with
  `-Wall -Wextra` **without warnings**, and links `libgame_jni.so` (phase 2),
  exporting exactly the 15 `Java_com_gamecore_NativeCore_*` symbols;
* the throwaway `jniLibs/host-check/` directory is removed again, so no host-built
  `.so` can ever be packaged.

## What none of this proves

OpenGL/EGL behaviour, shader compilation on a driver, the JVM resolving
`Java_com_gamecore_...` names, `System.loadLibrary` on Android, `BitmapFactory`,
`SoundPool`, `Vibrator`, window insets, Gradle/AGP, the **NDK** toolchain, or
anything device-specific.  There is no emulator run and no screenshot comparison.
