# Flare art import — technical reference for EMBERFALL unit sprites

Scope: analysis of the vendored Flare game data at `vendor/flare-game/` (sparse checkout:
`mods/` + `tiled/`) so the pygame RTS can switch from procedural rigs to blitting Flare
animation frames. Everything below was **read out of the actual files** (or measured with
PIL); where something is inferred or comes from the Flare engine source/docs instead of
this checkout, it says so explicitly.

Engine context: EMBERFALL renders a 1600×900 isometric view with 64×32 diamond tiles
(`sx=(x-y)*32, sy=(x+y)*16`), currently 4 facing buckets (`world.py::_set_bucket`
computes screen quadrants SE/NE/SW/NW), procedurally drawn today, switching to Flare blits.

---

## 1. Exact frame format

### 1.1 The `frame=` line — VERIFIED, 8 fields + optional 9th

Real lines, quoted verbatim from `vendor/flare-game/mods/fantasycore/animations/`:

```
image=images/avatar/male/buckler.png

[stance]
frames=4
duration=800ms
type=back_forth
frame=0,0,495,354,56,98,56,99
frame=0,1,1272,111,42,96,44,115
```
(`avatar/male/buckler.txt`, lines 5–12)

```
image=images/enemies/skeleton.png

[stance]
frames=4
duration=533ms
type=back_forth
frame=0,0,805,367,162,170,90,151
frame=0,1,0,1144,267,183,102,161
```
(`enemies/skeleton.txt`, lines 5–12)

```
image=images/enemies/minotaur/minotaur_stance.png,stance
image=images/enemies/minotaur/minotaur_run.png,run
...
frame=0,0,0,1092,157,248,76,227,stance
```
(`enemies/minotaur.txt`, lines 1 and 14 — note the **9th field**)

Field order confirmed by the official Flare engine attribute reference
([attribute-reference.html, AnimationSet section](https://raw.githubusercontent.com/flareteam/flare-engine/master/docs/attribute-reference.html)):

> **animation.frame** — `int, int, int, int, int, int, int, int, string : Index, Direction,
> X, Y, Width, Height, X offset, Y offset, Image ID` — "A single frame of a compressed
> animation. The image ID may be omitted, in which case the first available image will be
> used."

So:

| field | meaning | verified how |
|---|---|---|
| `index` | frame number **within this section**, `0 … frames-1` | every section's rows run 0..frames-1 (e.g. `run` has 8, `stance` 4, `die` 6) |
| `direction` | facing index `0…7` (see §2) | all 97,664 `frame=` lines in the checkout have this field; every value is 0–7 and all 8 occur in every sheet |
| `x`, `y` | top-left of the frame rect **inside the PNG** (pixels) | cropping `(x,y,x+w,y+h)` from the quoted `image=` sheet yields the sprite (PIL test) |
| `w`, `h` | size of that rect (pixels) | same test |
| `ox`, `oy` | offset of the **ground anchor point** measured from the rect's top-left; i.e. the rect must be blitted at `anchor − (ox, oy)` | see §5 — verified by compositing every direction/layer on a common ground cross |
| 9th `image ID` | optional; key matching the second token of an `image=path,ID` line | present only where a section uses its own sheet: `minotaur.txt`, `wyvern.txt`, `wyvern_air/fire/water.txt`, `empyrean…/wyvern_air_boss.txt` — 3,560 of 97,664 lines are 9-field, the other 94,104 are 8-field |

The parser must therefore accept both
`frame=index,dir,x,y,w,h,ox,oy` and `frame=index,dir,x,y,w,h,ox,oy,image_id`,
and must **not** choke on the 9-field form (an `int()` cast of the last token fails silently
and drops whole sheets).

### 1.2 Header keys actually present in the data

Counts across every `*/animations/**/*.txt` in all 7 mods (`grep '^[A-Za-z_]*='`):

```
97664 frame        2789 type        2789 frames      2789 duration
 519 image          62 active_frame  19 position      15 active_sub_frame
  7 color_mod        4 render_size    4 render_offset   1 alpha_mod
```

* **`image=images/avatar/male/buckler.png`** — path of the sprite sheet, relative to the
  mod root. Optional second token binds it to one section only:
  `image=images/enemies/minotaur/minotaur_stance.png,stance` (minotaur/wyvern use 7–8 of
  these; sections that have no *own* sheet — minotaur's `[hit]`/`[critdie]` — reference
  another bound sheet via their 9th field, e.g. `frame=0,0,330,907,157,248,76,227,die`
  pulls from `minotaur_die.png`).
  Sheets live under `mods/fantasycore/images/…` (also mirrored in empyrean/alpha_demo).
* **`[section]`** — animation state name. Observed set (whole checkout):
  `stance run run_alt swing block cast cast_alt shoot hit die critdie shield_bash
  dash_attack spawn power`. Avatar layers use exactly
  `stance run swing block hit die cast shoot` (all 66 male files).
* **`frames=N`** — number of frame indices in the section.
* **`duration=800ms`** — duration of the **whole** animation, not per frame
  (engine docs: "The duration of the entire animation in 'ms' or 's'"). Per-frame time is
  `duration/frames` when it divides evenly, otherwise spread with a Bresenham line
  (verified in flare-engine `src/Animation.cpp`). Examples:
  `stance` 800 ms / 4 = 200 ms per frame; `run` 533 ms / 8 ≈ 66.6 ms (≈15 fps);
  `block` 66 ms / 2 = 33 ms; `hit` 133 ms / 2; `die` 800 ms / 6; `swing`/`cast`/`shoot`
  400 ms / 4 = 100 ms. **Identical across all 66 avatar layers and (for the same
  animation) comparable across enemies** — measured, §3.
* **`type=play_once | back_forth | looped`** — the only three values in the data
  (all mods: 2,056 `play_once` / 391 `looped` / 341 `back_forth`;
  fantasycore alone: 1,083 / 201 / 178). `back_forth` ping-pongs (`stance` plays 0→3 then 3→0 —
  engine `Animation::advanceFrame`), `looped` wraps (`run`), `play_once` holds on the last
  frame (`die`, `swing`, …). This is the only playback-style key present; there is **no
  fps/rate key** — speed comes from `duration`. (Engine also supports a runtime
  `setSpeed()` multiplier; nothing in the data uses it.)
* **`position=0`** — only in `animations/hero.txt` and
  `animations/avatar/default_unpacked.txt`, the *unpacked* (grid) form: it is the index of
  the section's first cell in a shared `render_size` grid. `hero.txt` is a pure metadata
  file (no `frame=` lines at all):

  ```
  [stance]
  position=0
  frames=4
  duration=800ms
  type=back_forth
  ```
  and `default_unpacked.txt` begins:
  ```
  # This is a demonstration template file, not loaded by the engine.
  render_size=128,128
  render_offset=64,96
  ```
  So: **`render_size=128,128` / `render_offset=64,96` + `position=` = unpacked grid layout**
  (cell 128×128, shared anchor at (64,96) inside each cell) — we do **not** need to
  support it; every real avatar/enemy sheet in this checkout is *compressed* (explicit
  `frame=` rects).
* **`active_frame=`** (62 uses) — which frame index is the "hit connects" frame, e.g.
  `enemies/skeleton.txt` `[shield_bash] frames=2 duration=66ms type=play_once
  active_frame=0`. Value `all` appears 34 times across all mods (attacks/powers);
  engine default is the middle
  frame. Optional **`active_sub_frame=start|end|all`** (15 uses, e.g.
  `animations/powers/spear.txt: active_sub_frame=all`) decides which playback sub-tick
  fires it. Useful to us for melee timing; harmless to ignore at first.
* **`color_mod=R,G,B`** / **`alpha_mod=N`** — per-sheet tint/transparency. Real recipe
  (`empyrean_campaign/animations/enemies/zombie_ghost.txt`, complete file):
  ```
  color_mod=191,255,191
  alpha_mod=127

  INCLUDE animations/enemies/zombie.txt
  ```
  Other real tints: `frozen_zombie`/`skeleton_mage_ice` `color_mod=223,223,255`,
  `skeleton_mage_fire` `255,223,223`, `cursed_grave_ice` `207,207,255`,
  `antlion_fossilized` `60,50,45`. These are Flare's own elemental-variant recipe and are
  directly reusable for EMBERFALL frost/ghost units.
* **`INCLUDE animations/…`** — textual include (used by all `female_dark`, npc aliases and
  the tint variants above). A preprocessor that resolves `INCLUDE` before parsing gets all
  of these for free.
* `#flare_sprite_packer_input=…` / `#flare_sprite_packer_output=…` — comment lines with
  packer bookkeeping; ignore them.

### 1.3 `location=` and `set=` — NOT part of the animation format (verified absent)

* `location=` appears **zero times** under any `*/animations/**.txt`. The only
  `location=` in the checkout is in map files, e.g.
  `mods/empyrean_campaign/maps/merrimead_swamp.txt:278: location=2,15,1,4` (engine
  attribute reference: `enemygroup.location` = spawn rectangle, `npc.location` = point).
  **Do not implement `location=` for sprite import.**
* `set=` does not exist anywhere as a key. Grepping the whole vendor tree only matches the
  substring in `tileset=` lines (maps) — there is no per-section `set=` override in any
  animation file of this checkout. (Older Flare docs/versions may differ; this data does
  not use it.)
* `blend_mode=normal|add` is documented by the engine but appears **0 times** in the data.

---

## 2. Direction numbering

### 2.1 How many directions do the sheets actually have? — 8, everywhere

Counted distinct values of field 2 of every `frame=` line, per file:

* `fantasycore/animations/avatar/male/*.txt` — all 66 files: `0 1 2 3 4 5 6 7`
* `fantasycore/animations/enemies/*.txt` — all 19 files (antlion, antlion_small,
  cursed_grave, fire_ant, goblin, goblin_elite, goblin_elite_runner, goblin_runner,
  ice_ant, minotaur, skeleton, skeleton_weak, skeleton_archer, skeleton_mage, wyvern,
  wyvern_air/fire/water, zombie): `0 1 2 3 4 5 6 7`
* same for `empyrean_campaign` (incl. `skeleton_knight_boss`, `skeleton_mage_boss`,
  `skeleton_mage_high_boss`, `zombie_dark`, `hobgoblin`, `antlion_armored`),
  `alpha_demo` (necromancer, grisbon, scathelocke, vesuvvio) and `minicore`.

**No sheet in the checkout has fewer than 8 directions**; there is no 4-direction sheet
anywhere. All four "wyvern_air_boss" style big sheets also carry `0..7`. Corollary: we can
choose 4 *or* 8 facings without any asset limitation.

### 2.2 What the numbers mean — 0=SW … 7=S

The numeric→compass mapping is **not written in the game data** (the data only contains
0–7), but three independent sources agree:

1. **Official engine documentation**
   ([Flare attribute reference](https://raw.githubusercontent.com/flareteam/flare-engine/master/docs/attribute-reference.html),
   valuetype `direction`):
   > If defined as an integer, the value must be between 0-7 inclusive, mapping to
   > `["SW", "W", "NW", "N", "NE", "E", "SE", "S"]` respectively.
2. **`mods/fantasycore/engine/hero_layers.txt` lists its eight lines in exactly that
   order** — SW, W, NW, N, NE, E, SE, S (quoted in §3) — i.e. line *i* is direction *i*.
3. **Rendered check (mine):** I cropped `stance` frame 0 of all 8 directions for
   `skeleton`, `skeleton_archer` and a full 7-layer avatar stack, blitted each at
   `ground − (ox,oy)` and labelled them with the official mapping: dir 3 renders the back
   view (=N), dir 7 the straight-on front (=S), dirs 2/4 the two away-3/4 views
   (=NW/NE), dirs 1/5 the two profiles (=W/E), dirs 0/6 the near-3/4 views (=SW/SE).
   The art matches the mapping.

| index | compass | screen look (y down) | on our 64×32 iso grid |
|---|---|---|---|
| 0 | SW | down-left | moving **+y** (screen down-left) |
| 1 | W | left profile | — |
| 2 | NW | up-left | moving **−x** (screen up-left) |
| 3 | N | straight away (back) | — |
| 4 | NE | up-right | moving **−y** (screen up-right) |
| 5 | E | right profile | — |
| 6 | SE | down-right | moving **+x** (screen down-right) |
| 7 | S | straight toward camera (front) | — |

Male-avatar sheets and enemy sheets use the **same** numbering — verified by comparing
`hero_layers.txt` behaviour against enemy composites and by the identical field layout in
all files.

Direction from a movement vector (screen dx, dy; atan2 with y down, 0°=east):

```python
compass = (math.degrees(math.atan2(dy, dx)) + 90) % 360   # 0=N, clockwise
flare_dir = round((compass - 225) / 45) % 8               # 0=SW … 7=S
```

### 2.3 What our engine must implement — recommendation

* **Implement 8 directions.** All 97,664 frames ship all 8; the mapping above is 3 lines
  of code; 45° of motion resolution is noticeable for RTS units at close zoom, and Flare's
  art is authored for 8 (the profiles W/E exist and are the widest frames).
* **If we keep the existing 4 buckets**, they must be the four *diagonals* (that is what
  `world.py::_set_bucket` computes: bucket 0 = screen SE, 1 = NE, 2 = SW, 3 = NW), so the
  correct Flare indices are **SE→6, NE→4, SW→0, NW→2**, i.e. `DIRS = (6, 4, 0, 2)`.
* ⚠️ **Current-code discrepancy (reported, not modified):** `emberfall/src/flare_units.py`
  line 6 says *"Iso directions used: 7=SE, 5=NE, 1=SW, 3=NW"* and `DIRS = (7, 5, 1, 3)`.
  Per the official mapping and the checks above, `7=S, 5=E, 1=W, 3=N` — those four are
  each **one step (45°) away** from the labels, so every unit currently shows a
  cardinal-facing sprite when moving diagonally. Either relabel the buckets
  (7/5/1/3 = S/E/W/N) or change the tuple to `(6, 4, 0, 2)`; going 8-directional removes
  the issue entirely.

---

## 3. Layer draw order for the player character

### 3.1 Files available under `animations/avatar/male/` (66 files, with PNG twins in `images/avatar/male/`)

Every file has the same 8 sections (`stance run swing block hit die cast shoot`) and
identical `frames=`/`duration=`/`type=` per section (measured: exactly **1 distinct
combination across all 66 files for every section**).

Slot assignment is authoritative via `items/base/**` (`gfx=<name>` + `item_type=`):

* **base body** (no item; the always-drawn nude rig): `default_legs`, `default_feet`,
  `default_chest`, `default_hands` + hair `head_short`, `head_bald`
  (hair chosen by `engine/hero_options.txt`).
* **head**: `chain_coif`, `leather_hood`, `mage_hood`, `mage_hood_alt1`, `mage_hood_alt2`,
  `plate_helm`
* **chest**: `cloth_shirt`, `leather_chest`, `chain_cuirass`, `plate_cuirass`,
  `mage_vest`, `mage_vest_alt1`, `mage_vest_alt2`
* **hands**: `cloth_gloves`, `leather_gloves`, `chain_gloves`, `plate_gauntlets`,
  `mage_sleeves`, `mage_sleeves_alt1`, `mage_sleeves_alt2`
* **legs**: `cloth_pants`, `leather_pants`, `chain_greaves`, `plate_greaves`,
  `mage_skirt`, `mage_skirt_alt1`, `mage_skirt_alt2`
* **feet**: `cloth_sandals`, `leather_boots`, `chain_boots`, `plate_boots`, `mage_boots`,
  `mage_boots_alt1`, `mage_boots_alt2`
* **main hand** (`item_type=main`, 18): `battle_axe`, `club`, `dagger`, `greatstaff`,
  `greatsword`, `hand_axe`, `infantry_axe`, `longsword`, `mace`, `maul`,
  `reinforced_club`, `rod`, `shortsword`, `smith_hammer`, `staff`, `wand`, `war_hammer`,
  `zweihander`
* **off hand** (`item_type=off`, 8): `buckler`, `iron_buckler`, `kite_shield`, `shield`,
  and — note — **all bows/slingshots**: `longbow`, `shortbow`, `greatbow`, `slingshot`
  are off-hand items in Flare.

### 3.2 Draw order — `engine/hero_layers.txt` (verbatim, whole file)

```
# layer=direction, list of types in order of appearance, first item will be printed on screen first
layer=SW,main,feet,legs,hands,chest,off,head
layer=W,main,feet,legs,hands,chest,off,head
layer=NW,main,feet,legs,hands,chest,off,head
layer=N,feet,legs,hands,chest,off,head,main
layer=NE,feet,legs,hands,chest,off,head,main
layer=E,feet,legs,hands,chest,off,head,main
layer=SE,feet,legs,hands,main,chest,head,off
layer=S,main,feet,legs,hands,chest,head,off
```

"Printed first" = drawn first = **bottom of the stack**. Using the §2 index mapping
(lines are in direction order 0…7):

| dir | bottom → top |
|---|---|
| 0 SW, 1 W, 2 NW | main, feet, legs, hands, chest, off, head |
| 3 N, 4 NE, 5 E | feet, legs, hands, chest, off, head, main |
| 6 SE | feet, legs, hands, main, chest, head, off |
| 7 S | main, feet, legs, hands, chest, head, off |

### 3.3 How the layers stay in sync

* **Same key space:** every layer indexes frames by `(section, frame_index, direction)`.
  All 66 files define every key of every section (e.g. `stance` 4×8, `run` 8×8…).
* **Same timing:** `frames/duration/type` per section are byte-identical across all 66
  layers (measured, §3.1) — so frame *i* of `run` in `chain_cuirass` is the same instant
  as frame *i* of `run` in `longsword`. One shared playback clock drives every layer.
* **Origins are per-layer but reference the same ground point.** `ox,oy` are *crop
  relative*: each layer is packed in its own PNG, so the raw numbers differ wildly
  (mean |Δox| between `default_chest` and other layers ≈ 566 px — expected, meaningless on
  its own). What matters: `ground − (ox,oy)` puts every layer on the same character.
  **Verified:** compositing `chain_coif + chain_cuirass + chain_gloves + chain_greaves +
  chain_boots + longsword + buckler` for `stance` frame 0 in all 8 directions, each layer
  blitted with *its own* `ox,oy`, produces a perfectly registered knight (helm on
  shoulders, boots under greaves, sword in hand) for every direction; and stacking the 8
  `run` frames of one direction on one ground point keeps the feet in place (only the
  natural walk bob). If any layer's origin convention differed, the composite would shear
  immediately.

### 3.4 Z-fighting / pivot rules we must replicate

* **`main` (weapon) changes depth with direction:** bottom layer for dirs 0/1/2/7,
  *middle* (above hands, below chest) for dir 6, and **top-most** (over head!) for dirs
  3/4/5. A single fixed order for all facings is wrong: drawing the sword always on top
  buries the helm on S-facing frames where Flare intends it behind everything; drawing it
  always at the bottom hides the blade on N/NE/E-facing frames.
* **`off` (shield — and bows!) is above `head` only for dirs 6 (SE) and 7 (S)**, but under
  `head` for the other six. So the "shield behind body on back-facing frames" rule in
  Flare is actually: for N/NE/E the off-hand is drawn *after* `chest` (over the torso)
  yet *before* `head`/`main` — i.e. shield over the back, helm over shield, weapon over
  everything. Only when the shield arm is toward the camera (S/SE) does it go on top of
  the helm.
* **`feet` is drawn before `legs`** (boots bottom-most, greaves/pants over them) in Flare.
  The current rig (`BASE = [default_legs, default_feet, …]`, then e.g.
  `chain_greaves, … , chain_boots`) has the feet/legs pair reversed — visible where
  `chain_greaves` and `chain_boots` overlap at the ankle.
* Pivot: all layers share the same feet anchor (§5) — there is **no** per-layer pivot; a
  fixed per-direction order table plus one shared anchor is enough.

---

## 4. Enemy mapping table (EMBERFALL unit → exact Flare file)

Sizes are `stance` frame 0, direction 7 (=S), measured from the `.txt` rows; sheet pixel
sizes measured with PIL. "sections" = animation states available in that file.

| EMBERFALL unit | best available sheet (exact path under `mods/`) | why | what's missing / honest caveats |
|---|---|---|---|
| **Ghoul** | `fantasycore/images/enemies/zombie.png` + `fantasycore/animations/enemies/zombie.txt` (79×167 frame, sheet 3370×1788, 10 sections incl. `spawn`) | only shambling humanoid corpse; bloodied, hunched, correct 8-dir walk/die set | no hunched "ghoul" per se; for an elite use `empyrean_campaign/images/enemies/zombie_dark.png` (identical geometry, darker), for a spectral ghoul reuse Flare's own recipe: zombie + `color_mod=191,255,191` + `alpha_mod=127` (their `zombie_ghost.txt`) |
| **Crypt Fiend** | `fantasycore/images/enemies/antlion.png` + `animations/enemies/antlion.txt` (195×148 frame, sheet 1919×3225, 10 sections) | closest thing to a burrowing crypt-beast: low, wide, mandibles, 8-dir | **there is no spider/crustacean anywhere in the set** (filename search across all 7 mods + visual scan). Variants of the same base art: `fire_ant.png`, `ice_ant.png` (recolours, same rects), `antlion_small.png`; elite: `empyrean_campaign/images/enemies/antlion_armored.png` (291×222) |
| **Necromancer** | `fantasycore/images/enemies/skeleton_mage.png` + `animations/enemies/skeleton_mage.txt` (121×163 frame, sheet 2352×2874, 9 sections incl. `cast`, `shoot`) | robed skeletal caster with staff — same silhouette, same art set, 8 dirs, real cast animation | a *dedicated* `necromancer.png` exists but only in `alpha_demo/images/` (frame 27×55 — ≈⅓ the linear scale of fantasycore, different art generation: do not mix); elite caster: `empyrean_campaign/…/skeleton_mage_boss.png` (149×199) or `skeleton_mage_high_boss.png` (156×213). Note `assets/flare/enemies/defs/skeleton_mage.txt` currently drops the `shoot` section — use `cast` for attacks |
| **Abomination** | `fantasycore/images/enemies/minotaur/` (8 per-section PNGs, e.g. `minotaur_stance.png` 1802×1691) + `animations/enemies/minotaur.txt` (227×228 frame, 10 sections) | only big heavy melee brute in the set; axe + charge silhouette | **no flesh-golem/stitched-construct art exists** — minotaur is a compromise (horned beast-man). Uses 9-field `frame=…,stance` lines and per-section `image=path,ID` bindings — the importer must support both (or pre-merge sheets like `assets/flare/enemies/minotaur.png` already does) |
| **Frost Revenant** | `empyrean_campaign/images/enemies/skeleton_knight_boss.png` + `…/animations/enemies/skeleton_knight_boss.txt` (181×234 frame, sheet 3927×3420, 9 sections) **+ frost `color_mod=223,223,255`** | armoured skeleton warrior = revenant silhouette; the tint is Flare's own ice recipe (`frozen_zombie`, `skeleton_mage_ice` both use it) | **no ice/frost humanoid sheet exists**; the only "frozen" assets are tinted includes (`frozen_zombie.txt` = `INCLUDE zombie.txt` + `color_mod=223,223,255`). If a lighter revenant is wanted, that zombie-tint recipe is the fallback |
| **Skeleton** | `fantasycore/images/enemies/skeleton.png` + `animations/enemies/skeleton.txt` (125×170 frame, sheet 3886×2154, 10 sections incl. `shield_bash`) | exact match; shield + sword, full 8-dir set | variants available for tiers: `skeleton_weak.png` (bare bones, current mapping in `flare_units.py`), `skeleton_archer.png` (ranged), `skeleton_mage.png` (caster) |
| **Wolf / Elder Wolf** | **NO MATCH — none in the set** | searched every mod's image filenames (`wolf/dog/warg/hound/beast/boar/bear/rat/snake/horse`) and visually scanned all enemy sheets: the only canine asset is a *portrait icon* `fantasycore/images/portraits/dog01.png` | Flare has **no quadruped mammal at all**. Current `flare_units.py` maps `elder-wolf → goblin_elite`, which reads as a spear-wielding goblin, not a wolf. Honest options: (a) commission/reuse a canine sheet, (b) accept a non-canine stand-in and rename, (c) for a beast-boss feel use `fantasycore/…/wyvern.png` (199×190, 8-dir, per-section sheets) — nothing here honestly reads "wolf" |
| **Hollow King** (boss) | preferred: `empyrean_campaign/images/enemies/skeleton_mage_high_boss.png` + `…/skeleton_mage_high_boss.txt` (156×213 frame, sheet 3224×3243, 8 sections) — gold armour, purple cape, crown-like helm; alternative (current mapping): `…/skeleton_knight_boss.png` (armoured skeleton + red kite shield) | both are literally named "boss", 8 dirs, full run/swing/cast/die sets, larger than rank-and-file | neither has a dedicated "king" crown asset beyond the high-boss helm; there is **no undead-lord/lich sheet**. If a giant beast-boss is preferred: `empyrean_campaign/images/enemies/wyvern_air_boss/` (per-section sheets, 768×768 frames — huge, needs downscaling) |

Notes for the sim wiring:

* **Animation-state mapping** (EMBERFALL → Flare section): `idle→stance`, `walk→run`,
  `attack→swing` (melee) / `shoot` (bow users) / `cast` (casters), `death→die`.
  Flare ships **real death animations** (`die`, up to 6 frames, plus `critdie`) — better
  than faking death by rotating a live frame (what `flare_units.py::_compose_avatar` does
  today for `anim == "death"`).
* Sheets whose sections are *incomplete* (handle missing sections gracefully, fall back to
  `stance`): `cursed_grave` has only `stance cast hit die critdie` (static structure),
  `minicore/stealth` only `stance run hit swing` (**no death**), `skeleton_mage_boss` /
  `skeleton_mage_high_boss` 8 sections (no `shoot`), `boulder`/`goblin_minecart` 2.
* **Scale warning:** alpha_demo/minicore sheets are a *different pixel scale* (necromancer
  27×55, minicore skeletons ~21×25) — mixing them with fantasycore (160–250 px frames)
  without rescaling breaks silhouette consistency. Stick to fantasycore + empyrean.

---

## 5. Anchor / footprint guidance

### 5.1 The rule (verified)

`(ox, oy)` is the position of the unit's **ground contact point (feet)** inside the
frame rect, measured from the rect's top-left. To draw a unit whose logical ground point
projects to screen position `G`:

```python
dst_x = round(G.x - ox * s)      # s = sprite scale factor
dst_y = round(G.y - oy * s)
screen.blit(sheet, (dst_x, dst_y), pygame.Rect(x, y, w, h))   # rect from frame line
```

**Verification performed** (PIL composites, marker cross at `G`):

* `skeleton`/`skeleton_archer` `stance` frame 0, all 8 directions — every cross lands at
  the feet (between the boots, under the baked shadow), in every direction.
* A full 7-layer avatar stack, each layer using *its own* `ox,oy`, aligns perfectly on the
  cross in all 8 directions (§3.3).
* All 8 `run` frames of one direction anchored at the same `G`: the feet stay pinned to
  the cross (only the walk-cycle body bob moves).

The implied convention (engine returns `Renderable.offset` from the frame's
`render_offset` field; our composite confirms the sign) is exactly
`top_left = ground_anchor − offset`.

### 5.2 Why *not* bottom-centre

It is tempting to anchor at `(x + w/2, y + h)`, but:

* The crops are tight **content** rects that include the **baked drop shadow**, which
  extends to the lower-right *beyond* the feet. Measured on `skeleton` `stance` frame 0:
  `h − oy` = 19, 22, 16, 54, 56, 33, 28, 27 px for dirs 0…7 — bottom-of-rect is up to
  **56 px below the actual feet** (vendor scale) and it varies *per direction and per
  frame*. Bottom-anchoring makes units bob and swim when they turn or animate.
* Frame rects change size every frame (`run` dir 6 chain-cuirass frames vary), so any
  rule based on `w`/`h` rather than `ox/oy` jitters.

Concrete engine rule to implement:

```python
# precompute, per (sheet, frame): (x, y, w, h, ox, oy)
# per draw:
G = project_to_screen(unit.x, unit.y)          # 64x32 iso projection
dst = (round(G[0] - ox*s), round(G[1] - oy*s))
blit(surf.subsurface(x, y, w, h), dst)         # s already baked into surf & ox,oy
```

* Sort depth by `unit.y` (ground order), **not** by sprite bottom — the baked shadow
  inflates the bbox and would corrupt z-sorting.
* Flare's sprites carry their own soft shadow to the lower-right (light from top-left),
  which matches EMBERFALL's "top-left sun" art direction; don't add a second ellipse
  shadow under them (or draw a very faint one only at the anchor).

### 5.3 Scale for our window/tiles

Measured frame heights (dir 7, `stance` frame 0): zombie 167, skeleton 170, goblin 90,
antlion 148 (wide), minotaur 228, skeleton_knight_boss 234, avatar canvas 128
(`render_size=128,128`). Flare's own tiles are **192×96** isometric
(`mods/fantasycore/engine/tileset_config.txt: orientation=isometric / tile_size=192,96`).
Our tiles are 64×32 = exactly **1/3** of Flare's, so a 1/3 rescale preserves Flare's
proportions (unit ≈ 1.7 tile-heights tall, same as in Flare): skeleton 170→≈57 px,
zombie →≈56, minotaur →≈76–83, avatar →≈43 px body. The existing
`assets/flare/` derived sheets already follow this ≈1/3 convention (verified with PIL +
the defs: `w,h,ox,oy` equal `round(vendor/3)` within a few pixels — e.g.
`default_chest` stance d0 f0: vendor `83,109,23,118` → derived `27,33,8,39` — the small
deltas are re-trims of anti-aliased edge rows after downscaling; `x,y` are new pack
positions, and 9-field minotaur/wyvern frames were flattened to 8-field with the section
sheets merged). Keep that scale; if a unit is
rescaled by `s`, scale `ox,oy` by the same `s` (as `flare_units.py::sprite` already does
for its cached `ax,ay`).

⚠️ **Current-code discrepancy (reported, not modified):** `flare_units.py::_compose_avatar`
blits at `dx = 64 + ox - w/2`, `dy = 96 - oy - h`. The anchor that formula actually
produces is `(dx+ox, dy+oy) = (64 + 2·ox − w/2, 96 − h)` — it depends on the frame's crop
size, so the anchor shifts between frames and directions (and the reported `ay=84` doesn't
match the `96` used in the math). The verified rule for a fixed anchor `(64, 96)` is
`dx = 64 − ox`, `dy = 96 − oy`. The same pattern appears in `_compose_enemy`. Analysis
only — no code was changed here.

---

## 6. Licensing

The Flare art is licensed **CC-BY-SA 3.0 Unported** (the checkout's `vendor/flare-game/
LICENSE.txt` is the full "Attribution-ShareAlike 3.0 Unported" legal code; `CREDITS.txt`
credits the art primarily to **Clint Bellanger** (https://clintbellanger.net) "plus the
Flare contributors" — Justin Nichol, Jessica "Zeldyn" Cox, remaxim, rubberduck and others
listed under *Art* / *Additional Art*). Upstream: https://github.com/flareteam/flare-game,
license text: https://creativecommons.org/licenses/by-sa/3.0/. Any sprite we derive from
it — downscaled copies (`assets/flare/**`), repacks, team tints, `color_mod`-style
recolors, or frames drawn into EMBERFALL — is a **derivative work and must carry the same
CC-BY-SA 3.0 licence and attribution**: ship a credits line such as *"Unit art: Flare
(fantasycore) by Clint Bellanger and contributors — CC-BY-SA 3.0"*
(https://creativecommons.org/licenses/by-sa/3.0/) in-game and in the README.

---

## Appendix A — quick quotes for the importer test suite

```
# buckler (avatar off-hand layer), avatar/male/buckler.txt
frame=0,0,495,354,56,98,56,99        # stance f0 d0: x,y,w,h,ox,oy
frame=3,7,1683,224,76,89,48,81       # stance f3 d7
[run] frames=8 duration=533ms type=looped
[swing] frames=4 duration=400ms type=play_once

# skeleton enemy, enemies/skeleton.txt
frame=0,0,805,367,162,170,90,151     # stance f0 d0 (8-dir, back-3/4 by mapping dir0=SW)
frame=7,7,2775,179,194,182,119,160   # run f7 d7

# minotaur (per-section sheets + 9th field), enemies/minotaur.txt
image=images/enemies/minotaur/minotaur_stance.png,stance
frame=0,0,0,1092,157,248,76,227,stance
```

PIL-measured sheet sizes (selected): `avatar/male/default_chest.png` 2002×1166,
`avatar/male/longsword.png` 1855×1101, `avatar/male/buckler.png` 1901×805,
`enemies/skeleton.png` 3886×2154, `enemies/zombie.png` 3370×1788,
`enemies/skeleton_mage.png` 2352×2874, `enemies/goblin.png` 1316×3185,
`enemies/antlion.png` 1919×3225, `enemies/minotaur/minotaur_stance.png` 1802×1691,
`empyrean_campaign/images/enemies/skeleton_knight_boss.png` 3927×3420,
`empyrean_campaign/images/enemies/skeleton_mage_high_boss.png` 3224×3243,
`alpha_demo/images/enemies/necromancer.png` 961×666. All RGBA.

## Appendix B — claim → evidence index

| claim | evidence |
|---|---|
| frame fields order/names | official attribute reference (`animation.frame`) + 97,664 parsed lines |
| 8 directions on every sheet | distinct field-2 scan of every `frame=` line in all mods: `0..7`, no file with fewer |
| direction int → compass | official attribute reference (`direction` valuetype) + `hero_layers.txt` line order + rendered composites |
| `location=`/`set=` absent from animations | grep across all `*/animations/**.txt` (0 hits; `location=` only in maps) |
| timing keys | quoted `frames=4 / duration=800ms / type=back_forth` lines; engine `Animation.cpp` for sub-frame spacing & ping-pong |
| layer draw order | full quote of `engine/hero_layers.txt` |
| layers in sync | identical `frames/duration/type` across 66 files + multi-layer composite test |
| anchor = `ground − (ox,oy)` | direction/layer/run composites with marker cross (§5.1) |
| sheet dimensions | PIL `Image.open(...).size` over `avatar/male/*.png`, `enemies/*.png` (+ section subdirs) |
| licensing | `vendor/flare-game/LICENSE.txt`, `CREDITS.txt` |
