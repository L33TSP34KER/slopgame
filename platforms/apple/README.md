# Slime Arena — Apple (macOS + iOS) native renderer

Metal renderer for the shared game core (`core/` → `libgame_core.dylib`), for
macOS 13+ and iOS 15+. No third-party dependencies: AppKit, UIKit, Metal,
MetalKit, QuartzCore, CoreVideo and AVFoundation-less haptics only.

All gameplay lives in the core. This layer owns a window, a Metal context, the
textures, an input loop, the save blob and the speaker/haptics hook. It never
does game maths, camera work or text layout.

```
platforms/apple/
├── Package.swift                     SwiftPM: CGameCore + SlimeArenaRenderer + SlimeArenaMac
├── README.md                         this file
├── build_macos.sh                    cargo + swift build + assemble SlimeArena.app
├── build_ios_core.sh                 cross-compile the core, lipo, XCFramework
├── Packaging/
│   ├── macOS/Info.plist              copied into SlimeArena.app/Contents
│   └── iOS/Info.plist                INFOPLIST_FILE for the Xcode target
├── SlimeArena.xcodeproj/
│   └── project.pbxproj               one iOS app target (hand-written, objectVersion 56)
└── Sources/
    ├── CGameCore/                    C module for the frozen ABI (no implementation)
    │   ├── include/game_core.h       verbatim copy of include/game_core.h
    │   ├── include/module.modulemap  module CGameCore (SwiftPM *and* Xcode)
    │   └── shim.c                    _Static_asserts pinning gc_cmd/gc_input/gc_event/gc_status
    ├── SlimeArenaRenderer/           shared by both platforms
    │   ├── GameCore.swift            safe wrapper over the C ABI
    │   ├── MetalRenderer.swift       embedded MSL, batching, pipelines, vertex ring
    │   ├── TextureStore.swift        PNG loading, atlas, 1x1 white texture
    │   ├── Input.swift               GCInputState, VirtualJoystick, keyboard rules
    │   └── AudioHaptics.swift        event → haptics (real) and event → sound (hook)
    ├── SlimeArenaMac/                AppKit executable (SwiftPM)
    │   ├── main.swift                NSApplication in code, no storyboard
    │   ├── AppDelegate.swift         window, menu, fatal-error alert, save on quit
    │   ├── GameView.swift            CAMetalLayer view, input, frame loop
    │   └── DisplayLinkDriver.swift   CVDisplayLink → main-thread, coalesced ticks
    └── SlimeArenaIOS/                UIKit app source set (Xcode only, not SwiftPM)
        ├── AppDelegate.swift         classic lifecycle, background notification
        ├── GameViewController.swift  core + renderer + CADisplayLink + touch mapping
        ├── MetalView.swift           UIView with CAMetalLayer, forwards touches
        └── TouchControls.swift       DASH button + floating-stick overlay
```

## 1. Build the core first

`libgame_core.dylib` is produced by the Rust crate in `core/`. It must declare

```toml
[lib]
name = "game_core"
crate-type = ["cdylib"]
```

macOS / host:

```sh
cd core
cargo build --release
ls target/release/libgame_core.dylib      # or <repo>/target/release/... in a workspace
```

iOS cross-compilation targets (the exact `cargo` target triples):

| platform                  | cargo target             |
|---------------------------|--------------------------|
| iPhone / iPad (device)    | `aarch64-apple-ios`      |
| Simulator on Apple silicon| `aarch64-apple-ios-sim`  |
| Simulator on Intel Macs   | `x86_64-apple-ios`       |

`build_ios_core.sh` adds those targets with `rustup target add` when needed,
builds all three, `lipo`s the two simulator slices into one universal dylib, and
packs device + simulator into `build/ios/SlimeArenaCore.xcframework`.

## 2. macOS: build and run

```sh
platforms/apple/build_macos.sh
open platforms/apple/build/SlimeArena.app
```

What the script does, in order:

1. fails early with an explicit message if `cargo`, `swift`, `core/Cargo.toml` or
   the PNGs are missing;
2. refreshes `Sources/CGameCore/include/game_core.h` from `include/game_core.h`
   and **fails if the ABI version in the header and in `GameCore.swift` differ**;
3. `cargo build --release` in `core/`;
4. `swift build -c release`;
5. assembles `build/SlimeArena.app`:
   `Contents/MacOS/SlimeArenaMac`, `Contents/Frameworks/libgame_core.dylib`
   (`install_name_tool -id @rpath/libgame_core.dylib`, and the executable's load
   command rewritten to the same `@rpath` name),
   `Contents/Resources/Assets/*.png`, `Contents/Info.plist`, then ad-hoc signs
   the bundle (`install_name_tool` invalidates the signature on Apple silicon, and
   an invalid signature will not launch).

Manual equivalent, if you prefer:

```sh
cd core && cargo build --release && cd ..
cd platforms/apple
swift build -c release
swift run -c release SlimeArenaMac     # finds the dylib through an absolute rpath
```

Controls: **WASD / arrow keys** move, **mouse** aims, **left mouse** fires,
**space** dash, **esc** pause, **R** restart.

Assets are searched relative to the bundle: `Contents/Resources/Assets` first,
then `Assets`, `assets`, `dist`, `sprites`, then the bundle root — the loader
probes for `player.png`, so the folder name is not hard-coded.

SwiftPM note: `Sources/SlimeArenaIOS` is deliberately *not* a SwiftPM target (an
iOS app needs an `.app` bundle and an Xcode project). SwiftPM ignores that
directory; if it prints a warning about a source directory that no target covers,
it is expected and harmless.

Asset folder contents: the eight sprite PNGs plus `font_atlas.png`. The
`font_atlas.json` next to them is the UV table for the **core**, not for the
renderer — `gc_font_atlas()` returns the PNG's file name and the core emits
glyph commands with the atlas UVs already computed.

## 3. iOS: build and run

```sh
platforms/apple/build_ios_core.sh      # produces build/ios/... and the XCFramework
open platforms/apple/SlimeArena.xcodeproj
```

Then in Xcode: select the **SlimeArenaIOS** scheme, pick a simulator, set your
team (Signing & Capabilities) if you build for a device, and Run (⌘R).

The project is deliberately minimal: `objectVersion = 56`, one target, no test
targets, no asset catalog. It contains

* the ten compiled sources (five shared renderer files + four iOS files +
  `shim.c`),
* `Sources/CGameCore/include` on both `HEADER_SEARCH_PATHS` and
  `SWIFT_INCLUDE_PATHS`, which is what makes `import CGameCore` resolve exactly
  as it does under SwiftPM;
* `build/ios/current/libgame_core.dylib` in *Link Binary With Libraries* **and**
  in an *Embed Frameworks* copy phase (`dstSubfolderSpec = 10`,
  `CodeSignOnCopy`), so the dylib lands in `SlimeArena.app/Frameworks` and is
  found through `@executable_path/Frameworks`;
* a blue folder reference to `assets/dist`, added to *Copy Bundle Resources*;
* a first-position script phase that copies the core slice matching the SDK being
  built (`device/` or `simulator/`) into `build/ios/current/`. One
  `PBXFileReference` cannot vary per SDK, so this is how a single project builds
  for both.

Because `assets/dist` is produced by the asset pipeline, it may not exist in a
fresh checkout: the script phase prints a clear warning, and the resource copy
will fail until you either run the pipeline or re-point the blue `Assets` folder
at `assets/`. The runtime loader accepts either.

Controls: left half of the screen is a floating movement stick, right half is a
floating aim stick (`pointer_active = 1`, aim in virtual units), the round
**DASH** button sets `GC_BTN_DASH`. Backgrounding stops the `CADisplayLink` and
calls `gc_save` into `UserDefaults`; the blob is restored on launch.

### Fallback: create the iOS target by hand

If `SlimeArena.xcodeproj` does not open (it was written by hand and never opened
in Xcode):

1. Xcode → File → New → Project → iOS → App. Name it `SlimeArenaIOS`, Interface
   **Storyboard**, Language **Swift**. Delete `Main.storyboard`,
   `ViewController.swift`, `Assets.xcassets` and the `Info.plist` entries you do
   not need. (No storyboard is used: the app builds its window in code.)
2. Delete `GENERATE_INFOPLIST_FILE`, set **Info.plist File** to
   `Packaging/iOS/Info.plist`, and set **Supported Interface Orientations** to
   match it.
3. Drag `Sources/SlimeArenaRenderer` and `Sources/SlimeArenaIOS` into the
   project. For `AppDelegate.swift` make sure only the iOS one is in *Compile
   Sources* (the macOS shell is a different target).
4. Build Settings:
   * `SWIFT_INCLUDE_PATHS` = `$(SRCROOT)/Sources/CGameCore/include`
   * `HEADER_SEARCH_PATHS` = `$(SRCROOT)/Sources/CGameCore/include`
   * `LD_RUNPATH_SEARCH_PATHS` includes `@executable_path/Frameworks`
   * `IPHONEOS_DEPLOYMENT_TARGET` = 15.0, `SWIFT_VERSION` = 5.0
5. Drag `Sources/CGameCore/shim.c` in and leave it in *Compile Sources* (its
   `_Static_assert`s are the ABI guard).
6. Add `build/ios/current/libgame_core.dylib` (after running
   `build_ios_core.sh`) to *Link Binary With Libraries*, then add an **Embed
   Frameworks** copy phase (`Code Sign On Copy`, `Remove Headers on Copy`).
   For device/simulator flexibility add the run-script phase from the existing
   project (it is four lines of `cp`).
7. Drag `assets/dist` (or `assets/sprites`) in as a **folder reference** — blue
   folder, not a group — and add it to *Copy Bundle Resources*.

## 4. Design notes

### Commands and batching

`gc_cmds()` returns the frame's commands already in painter's order. The renderer
walks that buffer **once** and writes a pixel-space triangle list into a reused
`[GCVertex]`, rotating each quad on the CPU (in a y-down space a clockwise
rotation is the usual `(x·cos − y·sin, x·sin + y·cos)` matrix with a positive
angle). Consecutive commands that share *(texture, blend mode)* become one
`drawPrimitives` call; `GC_CMD_RECT` samples a 1×1 white texture, so rectangles,
sprites and glyphs all use the same pipeline and shader. Batches are recorded in
order and replayed in order, so reordering across a `texture`/blend change can
never break painter's order either.

The core's pointer is never handed to the GPU: its contents are copied into a
`MTLBuffer` before encoding. Three vertex buffers and a three-deep semaphore
(triple buffering) keep the CPU from overwriting a buffer the GPU still reads;
a buffer is only re-allocated when a frame genuinely needs more capacity than
the current one, and the Swift vertex array keeps its capacity between frames.

### Blend modes, FLASH and SHADOW

Two pipelines share the shader pair: normal
(`sourceAlpha` / `oneMinusSourceAlpha`) and additive (`sourceAlpha` / `one`) for
`GC_FLAG_FLASH`. Straight (`0xAARRGGBB`, non-premultiplied) alpha is preserved
end to end: the fragment shader returns `texture × vertexColour` without
premultiplying, and the blend state applies the source alpha once.

`GC_FLAG_SHADOW` needs no pipeline. While batching, the command emits a dark
(`rgb = 0`, `a = 45%` of the command alpha), offset copy of the same quad with
the same texture — so glyphs and sprites shadow their own silhouette — in the
normal-blend batch, immediately before the real quad. It costs six extra vertices
and usually no extra draw call.

`GC_CMD_GLYPH` uses the command's normalized `u0,v0,u1,v1` atlas rect (v grows
downwards); sprites use the whole texture; rectangles use the middle of the white
texel. Textures load with `MTKTextureLoader` using bilinear filtering, clamp to
edge and no mipmaps.

### Colour space

The drawable is `.bgra8Unorm` (not `_srgb`) and PNGs load with
`MTKTextureLoader.Option.SRGB = false`, so blending happens on the stored,
sRGB-encoded values — the usual 2D sprite-compositor convention, and the one
where the core's 8-bit colours land on screen as authored. Switching the layer to
`.bgra8Unorm_srgb` for physically linear blending requires flipping the texture
option at the same time (there is a comment in `TextureStore.swift`).

### Coordinates

Virtual units, y-down, origin at the framebuffer's top-left,
`pixel = virtual × gc_view_scale()`, and the design height is 720 virtual units,
so the scale is `framebuffer_height_px / 720`. There is no letterboxing and no
offset. macOS converts AppKit's y-up points with
`py = (bounds.height − point.y) × backingScaleFactor` (and documents why
`NSEvent.mouseLocation` needs a window conversion first); iOS needs no flip
because UIKit is already y-down. Aim is always in virtual units. iOS passes
`gc_resize` the **pixel** size and pixel safe-area insets, and keeps the drawable
size identical to it.

### Save blob

`gc_save` writes an opaque blob (best score, settings) into `UserDefaults`
(`com.slimearena.saveBlob`), restored with `gc_load` at launch — that is how the
best score survives. macOS saves on restart and on quit; iOS saves when the app
is backgrounded, after stopping the display link.

### Audio and haptics

Haptics are real: `AudioHaptics.swift` maps every `gc_event_type` to
`UIImpactFeedbackGenerator` / `UINotificationFeedbackGenerator` /
`UISelectionFeedbackGenerator` on iOS and `NSHapticFeedbackManager` on macOS,
with per-event throttling (shooting and XP pickups deliberately produce none).
Audio is an intentional no-op hook: the complete event → sound mapping lives in
`AudioMapping` (with stereo-pan hints), so implementing `AudioHook.play` and
passing it to `AudioHapticsDispatcher(audio:)` is the only change needed.

### Expected `gc_cmd` layout (56 bytes)

| offset | type       | field   | notes                                        |
|--------|------------|---------|----------------------------------------------|
| 0      | `int32_t`  | `kind`  | 1 sprite, 2 rect, 3 glyph                    |
| 4      | `int32_t`  | `sprite`| `gc_sprite_id`, sprite commands only         |
| 8      | `float`    | `x`     | **centre** of the quad, virtual units, y-down|
| 12     | `float`    | `y`     |                                              |
| 16     | `float`    | `w`     | size in virtual units                        |
| 20     | `float`    | `h`     |                                              |
| 24     | `float`    | `rot`   | clockwise radians about the centre           |
| 28     | `uint32_t` | `rgba`  | `0xAARRGGBB`, straight alpha                 |
| 32     | `float`    | `u0`    | glyph atlas UV rect                          |
| 36     | `float`    | `v0`    |                                              |
| 40     | `float`    | `u1`    |                                              |
| 44     | `float`    | `v1`    |                                              |
| 48     | `int32_t`  | `flags` | 1 flash/additive, 2 shadow                   |
| 52     | `int32_t`  | `_pad`  |                                              |

`gc_input` = 28 bytes, `gc_event` = 16 bytes, `gc_status` = 40 bytes. All of it
is asserted at C compile time in `Sources/CGameCore/shim.c` and re-checked in
`GameCore.verifyStructLayout()` at startup; `gc_abi_version()` is compared with
`GCABI.version` before any GPU work happens, and a mismatch throws a message that
says exactly what to rebuild.

## 5. VERIFICATION STATUS

**These sources have never been compiled.** They were written on a Linux host
with no Xcode, no Swift toolchain, no `cargo`-built core and no way to run any
Apple framework. Everything below is therefore *unverified*:

* no `swift build`, no `xcodebuild`, no `swiftc -parse` and no link step has ever
  run against these files;
* the Metal Shading Language string has never been compiled by
  `MTLDevice.makeLibrary(source:)`;
* `SlimeArena.xcodeproj/project.pbxproj` has never been opened by Xcode. It was
  validated structurally only: it parses as an OpenStep property list, all 50
  objects have unique 24-hex identifiers, every referenced identifier resolves,
  the build-phase order and `dstSubfolderSpec` are correct, and the group tree
  resolves to files that exist on disk — but Xcode's own model checks have not
  seen it;
* `build_macos.sh` and `build_ios_core.sh` pass `bash -n` and their ABI-version
  extraction was exercised against the checked-in header, but neither script has
  run to completion (no `cargo`, no `swift`, no `assets/dist` here);
* nothing has been run on a device, a simulator or a Retina display, so
  frame pacing, live-resize behaviour, safe-area handling and actual colours are
  all unconfirmed.

### What a macOS user should check first, in this order

1. `platforms/apple/build_macos.sh` — expect it to stop early and loudly if the
   core crate, `cargo`, `swift` or the PNGs are missing. Fix those first.
2. Compile errors in the shared module. Most likely candidates, in order:
   `MTKTextureLoader.Option.SRGB` / `MTKTextureLoader.Origin.topLeft.rawValue`
   spellings (`TextureStore.swift`), the `MTLVertexDescriptor` /
   `MemoryLayout.offset(of:)` block and the embedded MSL (`MetalRenderer.swift`),
   and the `gc_*` function signatures imported from `module.modulemap`
   (`GameCore.swift`).
   If SwiftPM itself complains about
   `Sources/CGameCore/include/module.modulemap`, delete that file: SwiftPM then
   generates an equivalent module map automatically (the Xcode project needs the
   file, so restore it before building for iOS).
3. The forward declaration of `_Static_assert`s in `shim.c`: if the core's header
   ever grows a field, this is where the build stops, by design.
4. Does the window open and does the clear colour appear? If the shader fails to
   compile, `MetalRenderer.Failure.libraryCompilationFailed` prints the MSL error
   text — read it, it points at the exact line.
5. Does anything draw? If `GC_CMD_RECT`s appear but sprites do not, the asset
   directory resolution in `TextureStore.locateAssets` or the PNG folder
   reference is wrong (the thrown message lists the directories it tried).
6. Is the image vertically flipped? That would mean the texture origin option and
   the core's UV convention disagree: try removing
   `MTKTextureLoader.Option.origin` from the options dictionary in
   `TextureStore.swift` — that is a one-line experiment.
7. Aim accuracy: click the four corners and confirm the crosshair follows. A
   consistent offset means the `gc_resize` pixel size and the drawable size
   disagree (check `updateFramebufferSize` in `GameView.swift`); a mirrored Y
   means the flip in `GCCoordinates.appKitPointToPixels` was applied twice.
8. Live-resize and moving the window between a Retina and a non-Retina display
   (`viewDidChangeBackingProperties`) — the drawable must not stretch.
9. Save blob: play, quit, relaunch — the best score should come back. If
   `gc_save` returns -1 forever, the core's save path is not implemented yet.
10. Console: `AudioHaptics` logs each unmapped sound in Debug builds, and
    `TextureStore.warnings` is logged once at startup.

### What to check first on iOS

1. `build_ios_core.sh` completes and `build/ios/current/libgame_core.dylib`
   exists and is a Mach-O for the right architecture (`lipo -info`).
2. The project opens; if not, follow the "Fallback" section above — it takes
   about five minutes and produces an equivalent target.
3. `import CGameCore` resolves (that is `SWIFT_INCLUDE_PATHS`).
4. The app launches into the clear colour; then that touching the left half moves
   and the right half aims. The stick overlay draws both, which makes a mapping
   mistake immediately visible.
5. Rotation: the image must not stretch after a rotation; check that
   `updateFramebufferSize` runs (it is also called once per frame, cheaply).
6. Backgrounding: the app must stop rendering and the best score must survive.
7. On a device without a developer team set, signing fails — set your team in
   Signing & Capabilities.

Nothing in this directory has been reviewed by anyone but its author, and no
claim here should be read as "it works". Treat the first build as a debugging
session.
