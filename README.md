# Slime Arena

A top-down wave-survival game built the way you asked for: **the entire game
logic lives in one shared library, and each platform ships a thin native
renderer that does nothing but draw, collect input and make noise.**

| Platform | Renderer | Status |
|---|---|---|
| Linux | Rust + SDL2 (hand-written FFI) | **built, run and screenshot-verified** |
| macOS | Swift + Metal (AppKit) | written, **never compiled** (no Xcode on the build host) |
| iOS | Swift + Metal (UIKit, touch sticks) | written, **never compiled** |
| Android | Kotlin + OpenGL ES 2 + JNI | JNI layer compiled & run against the real core; the app itself has **never been built** (no SDK/NDK) |

![Title screen](screenshots/01_title.png)
![Wave 9 combat](screenshots/08_combat_late.png)

---

## Quick start (Linux)

```bash
./tools/build_assets.sh          # sprite PNGs + font atlas  -> assets/dist
cargo run                        # builds libgame_core.so + the SDL2 renderer, then plays
```

Controls: **WASD/arrows** move, **mouse** aims, hold **left button** to aim
manually, **space** dash, **esc** pause, **R** restart.

No display? The renderer can drive itself headlessly and write PNGs:

```bash
cargo run -- --headless --scenario tour --out screenshots
```

Verification:

```bash
cargo test                       # 34 tests: unit + end-to-end through the C ABI
./tools/run_abi_harness.sh       # C harness: dlopen()s the .so and plays a full run
```

---

## Architecture

```
                    gc_cmd[]     (screen-space quads, painter's order)
   ┌───────────────┐ ─────────────────────────────────────────────▶ ┌──────────────────┐
   │ libgame_core  │      gc_event[]  (shoot / hit / die / level-up) │ Linux   SDL2     │
   │               │ ◀───────────────────────────────────────────── │ macOS   Metal    │
   │ ALL the game  │      gc_input    (move, aim, pointer, buttons)  │ iOS     Metal    │
   │ .so .dylib .a │ ─────────────────────────────────────────────▶ │ Android GLES2    │
   └───────────────┘      gc_status / gc_save / gc_load             └──────────────────┘
```

### What is inside the shared library

Simulation and fixed timestep, spawning and wave pacing, enemy AI, collision,
weapons and projectiles, damage/knockback/crit, pickups, XP and level-up card
selection, the shop economy, upgrades, particles and screen shake, the camera
and its arena clamping, **text layout**, glyph lookup and UVs, the whole HUD and
menu layout, and **UI hit testing**. Also: the save blob, and RNG determinism
(`gc_create(seed)` replays a run exactly).

### What a renderer does — and nothing else

1. Create a window and a GPU context.
2. Load `gc_sprite_file(i)` for every `i` in `[0, GC_SPR_COUNT)`, plus the font
   atlas from `gc_font_atlas()`.
3. Each frame: fill a `gc_input`, call `gc_update(handle, &input, dt)`, then walk
   `gc_cmds()` and draw, and forward `gc_events()` into sound and haptics.
4. Persist the opaque blob from `gc_save()` and hand it back to `gc_load()`.

A renderer never does game maths, never touches the camera, never lays out text.

### The contract: `include/game_core.h`

Frozen ABI, version-checked (`gc_abi_version()` must equal `GC_ABI_VERSION`).
The C harness `_Static_assert`s the struct sizes/offsets, and so does the Rust
side, so header drift is a build failure rather than a mystery on screen.

* **Commands** are `gc_cmd` (56 bytes): `kind`, `sprite`, `x/y/w/h`, `rot`,
  `rgba` (`0xAARRGGBB`, straight alpha), `u0..v1` (glyph atlas UVs), `flags`.
  Three kinds: `GC_CMD_SPRITE`, `GC_CMD_RECT` (UI/floor, no texture),
  `GC_CMD_GLYPH` (one character from the atlas).
* **`(x, y)` is always the centre** of the quad; `rot` is clockwise radians about
  that centre. Commands arrive **already sorted** — draw them in order.
* **`GC_FLAG_FLASH`** = additive blend (muzzle flashes, sparks, glow).
  **`GC_FLAG_SHADOW`** = draw a dark offset copy first (HUD text readability).
* **Coordinates** are *virtual units*, y-down, origin top-left, with the design
  height fixed at `GC_DESIGN_HEIGHT` (720). `gc_view_scale()` is the single
  uniform scale to physical pixels: `pixel = virtual * scale`. No letterboxing,
  no offset, so a renderer's projection is one multiply.
* **Layout is queried, not duplicated**: `gc_ui_slot(h, i)` /
  `gc_ui_slot_count(h)` / `gc_ui_button(h, which)` return the real rectangles of
  the clickable cards, shop items and buttons, in virtual units. That is how the
  automated tests click the UI, and how a shell can mirror it natively.
* The command/event pointers are owned by the library and valid until the next
  `gc_update`. Every entry point is thread-affine to the `gc_create()` thread,
  tolerates a NULL handle, and clamps garbage (`NaN`, absurd `dt`) instead of
  propagating it.

### Adding another platform (e.g. Windows)

1. Copy the sprite PNGs and `font_atlas.png` from `assets/dist/` into your bundle.
2. Build the core: `cargo build -p game_core --release` → `game_core.dll`.
3. Include `include/game_core.h`, load the DLL.
4. Write a loop: input → `gc_update` → draw `gc_cmds()` (one textured-quad
   pipeline + a 1×1 white texture is enough) → `gc_events()` → sound.
5. Build a projection with `gc_view_scale()` and convert pointer positions with
   `gc_pixels_to_virtual()`.
6. Run `tools/run_abi_harness.sh` first — if the C harness passes, your ABI
   plumbing is right.

---

## Repository layout

```
include/game_core.h          the frozen C ABI (the contract)
core/                        the shared library: all game logic, no dependencies
  src/{lib,world,systems,entities,render,render_world,ui,ffi,math,sprite}.rs
  src/generated/             tables generated from the art (aspects, glyph metrics)
  tests/gameplay.rs          15 end-to-end tests driven through the public ABI
platforms/linux/             SDL2 renderer (Rust + hand-written SDL2/libpng FFI)
platforms/apple/             Metal renderer: macOS app (SwiftPM) + iOS app (Xcode)
platforms/android/           Kotlin + GLES2 app, JNI wrapper, Gradle + CMake
assets/source-sheet.svg      the original art sheet
assets/sprites/*.svg         one sprite per file, extracted from the sheet
assets/dist/                 generated: 8 sprite PNGs + font atlas (bundled by every platform)
tools/build_assets.sh        art pipeline (source sheet -> dist + Rust tables)
tools/build_font.py          builds the shared bitmap font atlas + metrics
tools/extract_sprites.py     splits the source sheet into sprites
tools/harness/harness.c      C ABI conformance + full-run test against the .so
tools/run_abi_harness.sh     builds and runs the above
screenshots/                 headless captures (landscape + portrait)
prototype-bevy/              the original Bevy prototype, kept for reference
```

---

## Gameplay

* **Waves.** Enemies spawn off-screen, chase you and deal contact damage. Clear a
  wave → a bonus → **the Hive** → the next wave, bigger and faster.
* **Enemies.** Sixteen kinds, and every one is a row in a catalogue
  (`core/src/enemy_def.rs`) with a *behaviour* rather than a hand-written code
  path — so the whole bestiary is data:

  | Kind | Behaviour | Answer |
  |---|---|---|
  | Grunt, Brute, Colossus | Chaser | the baseline, and the two heavies |
  | Charger | Charger | coils, telegraphs, then crosses the arena at 3.4× |
  | Spitter | Shooter | holds a ring and lobs blood |
  | Lancer | Shooter | 430-unit standoff, fast 14-damage bolts |
  | Miser | Miser | lifts coins out of your purse and runs |
  | Wisp | Orbiter | circles at 155 units and never closes |
  | Blob | Splitter | bursts into three grunts |
  | Bulwark | Chaser + 45% armour | shrugs off chip damage; out-walk it |
  | Mender | Healer | mends every ally within 190 units |
  | Boomslime | Bomber | explodes for 22+ when killed next to you |
  | Shade | Blinker | teleports 240 units toward you every 2.6s |
  | Devourer | Grower | +7%/s health and damage while it lives |
  | Leech | Drainer | heals itself for 70% of what it takes off you |
  | Spiker | Trapper | leaves caltrops on the floor |

  Spawning is a weighted draw over the kinds whose `min_wave` has arrived, so
  the bestiary mixes itself; brutes and colossi stay rationed by the wave plan.
  Every kind also carries a visual tell — a mender's aura, a leech's red glow,
  a boomslime's pulsing fuse, a grower that visibly swells, a wisp's streak —
  plus the older set:
  * **Grunts** — fast, fragile, from wave 1.
  * **Brutes** — slow, 3× HP, from wave 3.
  * **Colossi** — from wave 5: 2.35× the size, huge health and damage, and they
    pay out ~20× a grunt. The risk/reward spawn.
  * **Chargers** (wave 2+) — stalk you, coil for half a second (a red blade
    telegraphs the exact line), then cross the arena at 3.4× speed. Sidestep or
    eat 19 damage; standing still is what kills you.
  * **Spitters** (wave 4+) — hold a 250-unit ring and lob blood clots that arc
    in and hurt for 9. Their sac brightens as a throw approaches.
  * **Misers** (wave 6+) — fast, cowardly pickpockets. Get close and they lift
    coins straight out of your purse (~2.5/s, up to 22). Once they have a haul
    they run, shedding coins behind them — kill one and it drops everything it
    took, plus its normal loot. Ignore them and the tax gets harder.
* **Weapons**, all auto-targeting the nearest enemy in range:
  `gun` (single bolt) · `bow` (3-arrow spread, pierces) ·
  `sword` (wide melee arc, knockback + slow).
* **XP levels are body stats only** — damage, fire rate, move speed, max HP,
  heal, magnet. The build-defining choices are bought.
* **The Hive (between every wave).** A honeycomb **upgrade tree of 313 nodes**:
  one `AWAKENING` root that everything hangs off, 39 chains of eight tiers, and
  keystone nodes that only unlock once you have a tier in *another* chain
  (Executioner needs Keen Eye III, Orbital Blade needs Sharper Steel II, …).
  The attack branch ends in a ghost army: **PHANTOM** (a chance that any kill
  leaves a phantom of the player behind), **PHANTOM FURY** (their damage),
  **PHANTOM SWARM** (how many can exist at once) and **TWIN FIRE** (a chance for
  any shot to be doubled). Phantoms drift around you, shoot on their own, and
  fade away after a few seconds.
  Drag to pan the hive, tap a node to buy it. The tree reveals itself one layer
  ahead, so it grows as you do.
* **Every 5 waves: a boss wave.** No mixed bag: one **enormous** enemy (16× the
  health, 3.1× the size, 2.4× the damage of its kind, worth 26× the loot) plus an
  escort that is entirely its own kind, so the wave has one readable idea. Bosses
  rotate through the kinds — brute, charger, spitter, miser, grunt — with a
  "BOSS WAVE" banner, a named health bar at the top of the screen, a gold halo
  and a crown marker so it is findable in a crowd. Kill it for a pile of coins.
* **Every 10 waves: a tax.** You must have *earned* in total by wave 10, 20,
  30… — **$750, $7 000, $65 333, $609 778, $5.69M, $53.1M** (clamped to $2B).
  That is a ×9.33 step per checkpoint, written into the source as the ratio
  `7000.0 / 750.0` so the two anchors are obvious.
  A step that steep demands compounding income — roughly +25% per *wave*. Coin
  value (`x(1 + 0.10 x wave)`) and the wave bounty grow linearly, so they cannot
  do it alone. **The Market is the answer**: see below. Without it the late tax
  is unreachable, which is why it exists. Meeting it is a checkpoint: a tier, a full heal and
  permanent power; missing it ends the run. The HUD turns the line red in the
  last three waves and tells you exactly how much is still missing. Because the
  tax counts *earnings*, spending money never sets you back. Both constants live
  at the top of `core/src/world.rs` if you want it crueller still.
* **The arena evolves.** Backdrop themes cycle with the waves — Hell → Gold →
  Lava → Paradise → Purple → Godly → back to Hell — interpolating smoothly, with
  per-run colour jitter and themed ambient particles (embers, dust, ash, motes,
  orbs, falling light).
* **Enemy movement.** Mobs steer rather than walk: they **lead your movement**
  (aiming up to 0.55 s ahead, so running in a straight line no longer shakes
  them), each one has its **own approach lane** so a wave encircles you instead
  of filing in behind its own front rank, they **slide around** whoever is in the
  way rather than shoving, a jammed enemy **sidesteps** after 0.45 s instead of
  grinding forever, and they keep off the arena walls.  Measured in the tests: a
  dozen grunts fanned over **2.5 rad** of the circle versus 1.2 rad when the
  lanes are removed — and they arrive *faster*, because they stop fighting each
  other's separation.
* **Feel.** Dash charges with i-frames and a trail, orbiting blades, lightning
  strikes, exploding rounds, thorns, lifesteal, auto-collected money, extra
  lives, hit flashes, knockback, floating damage numbers, death bursts, screen
  shake, spawn telegraphs, wave banners, low-health vignette, persistent best
  score.

### Controls

| | Move | Aim | Dash | Pause | Hive |
|---|---|---|---|---|---|
| Desktop | WASD / arrows | mouse (auto-aim + hold to aim) | space | esc / on-screen | drag or **mouse wheel** to pan, click to buy |
| iOS / Android | left stick | right stick (auto-aim always on) | on-screen button | back / on-screen | drag to pan, tap to buy |

---

## The Market

The upgrade *tree* is finite (313 nodes); the tax is not. Once the tree is
bought out there is nothing left to spend money on, and nothing that lets income
grow fast enough to chase a tax that multiplies by ~9.3 every ten waves. The
Market, opened from the **MARKET** button in the Hive (or `gc_market_set_open`),
fills that hole with four **uncapped** items whose prices grow geometrically, so
they stay a real decision at every point in a run:

| Item | Per level | First price | Price growth |
|---|---|---|---|
| **Compound Interest** | +2 % interest, paid on your whole purse every wave | $600 | ×1.75 |
| **Coin Mint** | +15 % value on every coin | $500 | ×1.70 |
| **Bounty Board** | +12 % wave bounty | $500 | ×1.70 |
| **Tax Rebate** | −3 % on every future checkpoint (floor 40 %) | $1,200 | ×2.00 |

Compound Interest is the important one: the tax compounds at ~1.25× per wave, and
interest is the only income source that can keep up, because it pays a cut of the
**purse** rather than a cut of the enemies you happened to kill. The intended late
game is therefore to stop buying and bank, letting the purse compound faster than
the tax — and to buy rebates when a checkpoint looks close. The panel shows your
current interest rate, because that number is the whole game by then.

There is a test for exactly this: it sets a plausible maxed state (tree interest
plus level-up cards plus twelve Market levels), banks the purse from wave 40, and
asserts the earnings by wave 50 cover the tier-4 checkpoint that a linear economy
could not touch.

## Installing on Android

A built APK is committed at `dist/android/` so it can be sideloaded without a
toolchain — download it on the phone, or:

```
adb install -r dist/android/slime-arena-debug.apk
```

It is a **universal** debug build (arm64-v8a, armeabi-v7a and x86_64), so it runs
on a modern phone and on an emulator alike.  It is signed with the debug key, so
it is for testing rather than the Play Store.  Rebuild it with
`tools/android/build_apk.sh` (or `... arm64-v8a` for a phone-only build, which is
about twice as fast).

## Options

`OPTIONS` sits under the primary button on the title and pause screens (and the
**O** key toggles it on desktop).  The overlay lives in the library, so every
platform gets the same menu; it is only available where a fight is not running,
and leaving the pause screen closes it rather than leaving a menu stuck over a
resumed run.

| Row | Notes |
|---|---|
| Music volume / Sound effects | 0–10; the renderer reads these through `gc_settings_get()` |
| Haptics | phones and tablets only |
| Screen shake | 0 turns the camera kick off entirely |
| Damage numbers | off leaves XP, money and level-up text alone |
| Particles | low / medium / high — the first thing to drop on weak hardware |
| Flashing | reduced keeps bright effects dimmer |
| Aim assist | blends a deliberate aim toward the nearest enemy |
| Fullscreen | borderless where the platform supports it |
| Restore defaults | puts everything back as it ships |

Clicking a slider's track sets it directly and dragging keeps following the
pointer; clicking elsewhere on a row steps it by one, so the menu is usable with
taps alone.  Settings are saved with the rest of the run data (the tail of the
same blob, so an older save simply keeps the defaults) and the options rows are
exposed as `gc_ui_button` slots `20..30` for shells that want to drive them.

## Audio

Sound is driven entirely by the core's event stream — the game logic never knows
whether a speaker exists.

**Music is yours to write.** Drop tracks into `assets/audio/music/` and they are
picked up at launch:

```
assets/audio/music/menu.ogg        <- the between-round hive (fades in and out)
assets/audio/music/hell.ogg        <- HELL      (waves 1-3)     \
assets/audio/music/gold.ogg        <- GOLD      (waves 4-6)      |
assets/audio/music/lava.ogg        <- LAVA      (waves 7-9)      | one per theme,
assets/audio/music/paradise.ogg    <- PARADISE  (waves 10-12)    | optional
assets/audio/music/purple.ogg      <- PURPLE    (waves 13-15)    |
assets/audio/music/godly.ogg       <- GODLY     (waves 16-18)   /
```

Any *other* `.ogg` in that folder joins a **rotation pool**, and a theme without
its own track uses `pool[theme % pool.len()]` in turn — so two tracks score a
whole run (the three tracks shipped here do exactly that), and adding a
per-theme file later overrides just that theme. `gc_theme_index()` reports the
current theme.

**Format: Ogg Vorbis.** The decoder is our own (`libvorbisfile`, streamed into
the mixer through `Mix_HookMusic`) because many distributions ship an SDL2_mixer
built with no codec support at all — the one on this machine links nothing but
SDL2, so `Mix_LoadMUS` cannot open even a plain `.ogg`. Use the importer to
convert anything:

```
tools/import_music.sh "My Song.m4a"          -> assets/audio/music/my_song.ogg
tools/import_music.sh "Boss Theme.flac" hell -> assets/audio/music/hell.ogg
```

Tracks loop forever and the switch is a **1.4 s cross-fade** — the outgoing track
fades out while the new one fades in, and the menu track does the same when the
hive opens and closes. Write them to loop cleanly.

**Sound effects are synthesised** (swept tones and noise, generated into a WAV in
memory at startup), so there is sound without a single asset file. Any cue can be
replaced individually by dropping `assets/audio/sfx/<cue>.wav` next to it — the
cue names are `shoot, hit, enemy_die, player_hurt, pickup_xp, pickup_money,
level_up, buy, buy_fail, wave_start, wave_clear, game_over, ui_click, dash,
lightning, checkpoint_passed, checkpoint_failed, revived`. Cues are rate-limited
(shoot 45 ms, hurt 180 ms, …) so a swarm cannot turn into noise.

**Every cue ships with five detuned takes** and a random one is chosen per play,
so repeated shots never sound like a machine. Each take varies its pitch
(±2 % for melodic cues like level-up and checkpoints, ±10 % for percussive ones
like shots, hits and lightning), its speed (0.92–1.10×, which also changes the
length) and its level (0.85–1.05×). Your own `.wav` overrides get the same
treatment: they are decoded and resampled into five takes, so a file dropped in
is detuned too. The take RNG is seeded, so a given run sounds the same twice.

Keys: **M** mute, **-**/**=** music volume. `--no-audio` runs silent, and
headless mode is silent unless you pass `--audio`.

## Asset pipeline

`assets/source-sheet.svg` is the design sheet. `tools/build_assets.sh` runs:

1. **`extract_sprites.py`** — finds each sprite group in the sheet by its geometry
   and writes one standalone SVG per sprite, keeping the original coordinates.
2. **`build_sprites.py`** — rasterises each sprite (512 px wide, aspect preserved),
   trims the transparent padding and writes `assets/dist/*.png`, then generates
   `core/src/generated/sprites.rs` (file names + aspect ratios). Because the art
   is tight-trimmed, the library can emit undistorted quads at any world size.
3. **`build_font.py`** — renders the printable ASCII range from a system bold sans
   font, measures each glyph's ink box and advance with ImageMagick, packs a
   white-on-transparent atlas, and generates `core/src/generated/font_metrics.rs`.

The font is deliberately a **shared bitmap atlas**: the library emits one
`GC_CMD_GLYPH` per character with atlas UVs, so typography is pixel-identical on
every platform and no renderer needs a font API. `build_font.py` also writes
`assets/font_verify.png`, which renders a sample string *from the atlas* next to
ImageMagick's own rendering of the same string — a quick eyeball check that the
metrics are right.

---

## Verification status

Everything below was actually executed on the Linux build host.

| Check | Result |
|---|---|
| `cargo test` | **107 passed** — 82 core unit (tree structure, tax curve, backdrop and scenery, settings, enemy behaviours, ABI layout, layout maths), 10 renderer unit (audio synthesis, detuned takes, WAV decode, Vorbis decode checked against ffmpeg and against a stutter/rate regression) and 15 end-to-end through the C ABI |
| `tools/run_abi_harness.sh` | **PASSED** — C program `dlopen`s the real `.so`, `_Static_assert`s the ABI, and plays a whole run (~735 frames, 17 838 sprite / 69 784 glyph / 148 648 rect commands) including a hive purchase at exactly the quoted price, a locked node refusing to sell, a drag that must not buy, level-up, pause, save/load and restart |
| Linux renderer | builds warning-free, loads `libgame_core.so` at runtime (`dlopen`), runs headless |
| Headless captures | 9 landscape + 9 portrait (1170×2532) PNGs in `screenshots/`, generated from scripted input by clicking the *real* UI rectangles |
| Determinism | a test drives two identical seeds through 600 scripted frames and asserts the command streams are byte-identical; a different seed must diverge |
| Robustness | `NaN`/infinite aim, `dt = 1e-6 … 100`, absurd framebuffer sizes and 4000 frames of button-mashing must never produce a broken frame |
| Sprite colours | verified pixel-for-pixel against the source PNGs (`player`, `enemy_a`, `money`, `xp`) |
| Apple Swift/Metal | **never compiled** — no Xcode/swiftc on this host. See `platforms/apple/README.md` |
| Android app | JNI wrapper compiled and run on the host against the real core (900 frames); the Gradle app itself **was never built** — no SDK/NDK/working Gradle. See `platforms/android/README.md` |

Bugs the tests caught during development, for the record: non-finite input from a
renderer used to propagate into player positions; events were cleared per fixed
step so a frame with several steps only reported the last one's; and the Linux
renderer drew `GC_CMD_RECT` with a fill call that cannot rotate, so hexagon
edges, bullets and particles were all axis-aligned (the Apple and Android
renderers were already correct).

---

## Known gaps / next steps

* **No audio yet.** Every sound-worthy event is already in the ABI
  (`GC_EVT_SHOOT`, `GC_EVT_HIT`, `GC_EVT_ENEMY_DIE`, …) and each renderer maps
  them; only the samples/synth are missing.
* **Apple and Android apps need their toolchains**: Xcode for iOS/macOS, SDK +
  NDK for Android (`rustup target add aarch64-linux-android` etc.). Both READMEs
  list exactly what to check first.
* **No Windows renderer** — the recipe above is complete; it is a few hundred
  lines of Win32 + D3D11 or SDL2 and needs no changes to the core.
* The tree is data: `core/src/tree.rs` holds one line per family, so adding a
  branch, a keystone or a whole new stat axis is a table edit plus one arm in
  `Stats::add`. New enemies are a match arm in `EnemyKind`.
