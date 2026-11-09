# EMBERFALL — Flare terrain tile sheets

Owner: terrain-art agent.  Files owned: `assets/flare/raw/tiles/emberfall_*.png`,
`design/notes/flare-tiles.md`, `design/notes/tiles-*.png`, `design/notes/tiles-tmp/**`.

Builder (reproducible): `design/notes/tiles-tmp/build_tiles.py`
Verifier: `design/notes/tiles-tmp/verify_tiles.py`  ·  Raw numbers: `design/notes/tiles-tmp/report.json`

---

## 1. What was wrong and what these sheets do

Players reported the ground "reads as a diamond lattice / test pattern" and that biome
transitions are hard cuts.  Measured causes:

1. **Every source diamond has a 1-px alpha edge at exactly `f = 1`.**  In iso layout two
   abutting tiles each present alpha ≈ 0.56 on that shared line, so the composited seam
   comes out at alpha ≈ 206/255 — a translucent hairline around *every* diamond.  Over
   dark ground that is precisely a dark lattice.
2. **The 16 grass tiles are near-clones** (mean-colour deviation ≤ 1.2 levels across the
   row), so the field repeats visibly even before the lattice is added.
3. There was **no transition art at all** — biome changes were tile-to-tile colour cuts.

The sheets fix all three: exact-lattice opaque alpha, a shared lattice-periodic *rim
reference* that makes both sides of every boundary the same colour, per-tile brightness
variation, and a full set of half-blend / feathered transition tiles.

---

## 2. Geometry contract (all three sheets)

* Tile = **64×32 RGBA**, diamond centred on **(32, 16)**, pixel centres at `(i+0.5, j+0.5)`.
* `f = |px−32|/32 + |py−16|/16`; `alpha = 255` for `f ≤ 1`, else `0` (no feather).
* Diamonds centred on the iso lattice `(32+32(c−r), 16+16(c+r))` tile the plane exactly,
  and because pixel centres sit on the half-integers **no pixel centre ever lands on a
  diamond edge**, so every composited pixel is owned by exactly one tile at alpha 255.
  → zero translucent seams, zero holes (verified: `gap_px = 0`, `min_alpha = 255`).
* Cell corners are transparent (`f ≈ 1.95`), cell centre opaque.  50 % of each sheet is
  transparent — no baked background, no labels.

**Rim blending (the seam fix).**  Each tile's RGB is blended toward a per-row reference
image over `f = 0.52 → 0.90` (≈5.4 px) and is **exactly** that reference for `f ≥ 0.90`
(the outer 1.4 px, which is where every inter-tile boundary lives).  The reference is:

```
g(u)   = alpha-weighted mean of the row's 16 tiles   (outer 10 % excluded: LANCZOS
                                                      ringing after 3:1 downscale)
g      -> circular box blur (wraps, so it stays cell-periodic)
h(u)   = ( g(u) + g(u − (32,16)) ) / 2               phase average over {(0,0),(32,16)}
```

Lattice vectors are congruent to `(0,0)` or `(32,16)` modulo the 64×32 cell and
`2·(32,16)` is one full cell wrap, so `h(u) == h(u − (32,16))` **exactly**.  Two tiles
therefore sample *identical* rim colour at a shared boundary → seam delta is only `h`'s
own 1-px gradient (≤ 0.9 levels measured).

**Per-tile variation.**  Every source tile is first normalised to the row's mean
luminance, then given a global gain in **±3.5 %** plus a smooth zero-mean spatial drift
of **±3 %**, so no two adjacent tiles read the same (measured spread −3.6 %…+3.6 %,
0 duplicate tiles, min adjacent mean-colour difference 4.3 levels).  Both are applied
*before* the rim blend, so the rim — and therefore the seam — is unaffected.

---

## 3. `emberfall_ground.png` — 1024×256, 8 rows × 16 tiles (194 KB)

Row index → biome.  Crop coords are `x = col × src_w`, `y = row_y`, `src_w × src_h`,
LANCZOS-downscaled to 64×32 when the source is 3×.

| # | row | source atlas | crop (y, cell) | tint (R,G,B) | ref L |
|---|-----|--------------|----------------|--------------|-------|
| 0 | `grass`     | `assets/flare/raw/tiles/grassland.png`   | **y=96**,  64×32 cells, col 0–15 | `(1.00,1.00,1.00)` | 82.2 |
| 1 | `grass_dry` | `assets/flare/raw/tiles/grassland.png`   | **y=96**,  64×32 cells | `(1.28,1.02,0.86)` | 89.3 |
| 2 | `dirt`      | `vendor/flare-game/tiled/tilesheets/ruins.png` | **y=2208**, 192×96 cells | `(1.78,1.78,1.78)` | 75.8 |
| 3 | `dirt_road` | `vendor/flare-game/tiled/tilesheets/cave.png`   | **y=288**,  192×96 cells | `(1.51,1.51,1.51)` | 80.5 |
| 4 | `sand`      | `vendor/flare-game/tiled/tilesheets/snowplains.png` | **y=288**, 192×96 cells | `(0.531,0.472,0.404)` | 100.2 |
| 5 | `ash`       | `vendor/flare-game/tiled/tilesheets/snowplains.png` | **y=672**, 192×96 cells | `(0.457,0.419,0.390)` | 76.1 |
| 6 | `stone`     | `assets/flare/raw/tiles/grassland.png`   | **y=224**,  64×32 cells, col 0–15 | `(1.00,0.98,1.06)` | 82.2 |
| 7 | `moss`      | `vendor/flare-game/tiled/tilesheets/grassland.png` | **y=288**, 192×96 cells | `(0.94,1.31,1.33)` | 86.9 |

Notes:

* `grass` and `stone` are the exact rows the current loader already reads
  (`floor_sources()` → y=96 and y=224), so those two stay pixel-familiar.
* All eight rows are **real Flare diamonds**; the tint column is a plain per-row RGB
  multiply (same mechanism `flare_terrain.TINTS` already uses) applied after cropping.
* Rows were deliberately kept in a **narrow luminance band (76–100)** so that the neutral
  rim used by the edge sheet stays close to every pure row (see §5 caveat).

---

## 4. `emberfall_edges.png` — 1024×256, 8 rows × 16 tiles (184 KB)

Row order (both halves take their textures from the two ground rows above):

| # | row key | A (material) | B (material) |
|---|---------|--------------|--------------|
| 0 | `grass__dirt`   | grass 82.2 | dirt 75.8 |
| 1 | `grass__sand`   | grass 82.2 | sand 100.2 |
| 2 | `grass__ash`    | grass 82.2 | ash 76.1 |
| 3 | `grass__stone`  | grass 82.2 | stone 82.2 |
| 4 | `dirt__road`    | dirt 75.8 | dirt_road 80.5 |
| 5 | `grass__moss`   | grass 82.2 | moss 86.9 |
| 6 | `ash__stone`    | ash 76.1 | stone 82.2 |
| 7 | `dirt__sand`    | dirt 75.8 | sand 100.2 |

**Columns 0–7 — directional half-blends.**  Boundary line through the diamond centre at
screen angle `θ = 78.75° − 22.5°·k` (k = 0…7, y down), material **A** on the side the
normal `n = (cos φ, sin φ)`, `φ = −(k+0.5)·22.5°`, points away from; blend width **8 px**
smoothstep plus ±1.6 px of organic noise on the seam.

**Columns 8–15 — feathered variants.**  Same eight angles, but the seam is driven by a
±5.5 px low-frequency noise field over a **14 px** blend, so the A/B boundary is mottled
rather than straight.

Both halves blend to the rim over the same `f = 0.52 → 0.90` band as the ground rows.

---

## 5. Edge rim — one neutral reference per row, and why

Because an edge tile sits between two materials, its rim colour is fixed to
`½·(refA + refB)` **for the whole row** (a lattice-periodic image, same construction as
§2).  That is a deliberate geometric choice, not a shortcut:

* Edge tiles are always adjacent to each other *along* a boundary (row-neighbours) and to
  pure tiles *across* it (col-neighbours).  A rim that tried to be `refA` on the A arc and
  `refB` on the B arc cannot be lattice-periodic — it forces `m(32) ≠ m(96)` — so such a
  rim makes every boundary-running line of edge tiles cut a hard `|refA − refB|` line into
  its own row.  The neutral rim makes edge↔edge seams **0.0** and edge↔pure seams
  `½·|refA − refB|`.
* Because §3 keeps all rows in a 76–100 luminance band, `½·|ΔL|` is **≤ 6 levels for every
  pair except those involving `sand`**:

| pair | rim L | ½·\|ΔL\| vs A | vs B |
|------|-------|------|------|
| grass__dirt | 79.0 | 3.2 | 3.2 |
| grass__sand | 91.2 | **9.0** | **9.0** |
| grass__ash  | 79.1 | 3.1 | 3.0 |
| grass__stone| 82.2 | 0.0 | 0.0 |
| dirt__road  | 78.1 | 2.3 | 2.4 |
| grass__moss | 84.5 | 2.3 | 2.4 |
| ash__stone  | 79.1 | 3.0 | 3.1 |
| dirt__sand  | 88.0 | **12.1** | **12.1** |

  If `grass|sand` / `dirt|sand` boundaries show a faint 1-px rim in play, pull the sand
  row's tint down toward `L ≈ 90` (change one multiplier in `GROUND`) and rebuild — that
  costs nothing else.

---

## 6. `emberfall_water.png` — 1024×64, 2 rows × 16 tiles (37 KB)

Source for both rows: `assets/flare/raw/tiles/grassland_water.png` **y=160**, 64×32
cells, col 0–15 — the only clean, full-coverage water row in that atlas.  (The row the
old loader reads, `y=32`, contains shoreline cliffs, docks and foam dashes; it is *not*
used here, which is why the sheet has "no per-tile outlines, no dashes".)

**Row 0 — deep → shallow, cols 0…15.**  Each tile is the base water texture shifted so
its mean lands on `lerp((34,48,58), (96,132,130), col/15)` — 5.07 luminance steps per
column, i.e. a smooth 77-level depth ramp.  Flat water, no outlines, no dashes.

**Row 1 — 8 feathered shore edges + 8 more.**
* cols 0–7: `water|sand` directional shore, same 8 angles and 8 px blend as the edge sheet.
* cols 8–15: `water|sand` **feathered** shore, ±5.0 px noise over a 14 px blend.
* The whole row shares one rim reference (`½·(refWater + refSand)`, L = 78.3).

---

## 7. Suggested loader mapping (one edit in `emberfall/src/flare_terrain.py`)

Replace `floor_sources()` / `water_sources()` and add `edge_sources()`; drop `TINTS`,
`BASE_KIND` and `LIGHT` (colours are baked now).

```python
GROUND_ROWS = ["grass", "grass_dry", "dirt", "dirt_road",
               "sand", "ash", "stone", "moss"]                      # y = i*32
EDGE_ROWS   = ["grass__dirt", "grass__sand", "grass__ash", "grass__stone",
               "dirt__road", "grass__moss", "ash__stone", "dirt__sand"]

def _rows(name, n):
    sheet = _load(name)
    if sheet is None:
        return {}
    out = {}
    for i in range(n):
        out[i] = [sheet.subsurface(pygame.Rect(c * 64, i * 32, 64, 32)).copy()
                  for c in range(16)]
    return out

def floor_sources():
    """{biome_name: [16 x 64x32 diamonds]} from emberfall_ground.png"""
    rows = _rows("emberfall_ground.png", 8)
    return {GROUND_ROWS[i]: rows[i] for i in rows} or _legacy_floor_sources()

def edge_sources():
    """{pair_key: [16 x 64x32]}; cols 0-7 directional, 8-15 feathered."""
    rows = _rows("emberfall_edges.png", 8)
    return {EDGE_ROWS[i]: rows[i] for i in rows}

def water_sources():
    """{'depth': [16 deep->shallow], 'shore': [16 water|sand]}"""
    rows = _rows("emberfall_water.png", 2)
    if not rows:
        return _legacy_water_sources()
    return {"depth": rows[0], "shore": rows[1]}
```

Placement rules for the engine:

* Pick a random column `0–15` per map cell (any column is safe — no duplicates side by side).
* At a biome boundary running **col-wise** on screen (the classic iso horizontal boundary)
  use `edge_sources()[pair]`: column `k` matches a boundary whose screen angle is
  `78.75° − 22.5°·k`; use the feathered columns 8–15 when the boundary is irregular.
* Water: index the depth row by water depth (`0 = deepest`), and place a shore tile where
  water meets sand.

---

## 8. Quality-gate numbers (all measured, `report.json`)

**Sheet geometry / alpha** — `verify_tiles.py`:

| file | size | mode | tiles | corner violations | non-opaque cores | transparent frac | KB |
|------|------|------|-------|-------------------|------------------|------------------|----|
| `emberfall_ground.png` | 1024×256 | RGBA | 8×16 | 0 | 0 | 0.500 | 194 |
| `emberfall_edges.png`  | 1024×256 | RGBA | 8×16 | 0 | 0 | 0.500 | 184 |
| `emberfall_water.png`  | 1024×64  | RGBA | 2×16 | 0 | 0 | 0.500 | 37 |

All < 1.5 MB.  Ground rows: 0 duplicate tiles, brightness spread **−3.6 % … +3.6 %**,
min adjacent-tile mean-colour difference 4.3 levels.

**Seam test** — 6×6 iso composite of the row's tiles, max |Δ luminance| across internal
tile boundaries (target ≤ 6):

| sheet | row | max | mean | holes | min alpha |
|-------|-----|-----|------|-------|-----------|
| ground | grass | **0.34** | 0.10 | 0 | 255 |
| ground | grass_dry | **0.37** | 0.11 | 0 | 255 |
| ground | dirt | **0.31** | 0.09 | 0 | 255 |
| ground | dirt_road | **0.39** | 0.11 | 0 | 255 |
| ground | sand | **0.12** | 0.03 | 0 | 255 |
| ground | ash | **0.89** | 0.21 | 0 | 255 |
| ground | stone | **0.78** | 0.21 | 0 | 255 |
| ground | moss | **0.43** | 0.13 | 0 | 255 |
| edges | grass\|dirt | **0.24** | 0.06 | 0 | 255 |
| edges | grass\|sand | **0.20** | 0.05 | 0 | 255 |
| edges | grass\|ash | **0.41** | 0.12 | 0 | 255 |
| edges | grass\|stone | **0.38** | 0.11 | 0 | 255 |
| edges | dirt\|road | **0.27** | 0.08 | 0 | 255 |
| edges | grass\|moss | **0.37** | 0.11 | 0 | 255 |
| edges | ash\|stone | **0.66** | 0.19 | 0 | 255 |
| edges | dirt\|sand | **0.14** | 0.04 | 0 | 255 |
| water | depth (row 0) | **5.12** | 2.59 | 0 | 255 |
| water | shore (row 1) | **0.07** | 0.02 | 0 | 255 |

Sheet worst cases: **ground 0.89**, **edges 0.66**, **water 5.12** — all ≤ 6.
(The water depth row is a *designed* gradient: 5.07 levels between adjacent depth
columns; the patch is laid out so neighbouring cells are adjacent depth steps.)

**Transition strip** — `design/notes/tiles-transition.png`, grass → dirt → stone,
6×14 iso, 320×640:

| metric | value |
|--------|-------|
| seam max across tile boundaries | **5.15** |
| seam mean across tile boundaries | **0.62** |
| mean pixel step **inside** tiles (painted texture) | **3.18** |
| mean pixel step **on** tile boundaries | **0.58** |
| boundary p95 | 3.38 |
| max column mean gradient / median | 5.96 / 2.90 = 2.06 |
| holes in interior / min alpha | 0 / 255 |

A hard cut would make the boundary the *largest* number in the image; instead tile
boundaries are **5.5× smoother than the painted texture itself** (0.58 vs 3.18), and the
two biome boundaries in the strip are visibly feathered — **no straight line**.
(The 2.06 column ratio is texture contrast: the largest single-pixel jumps in the strip
occur *inside* tiles, where the painted pebbles are.)

**Montages to look at** (all in `design/notes/`):
`tiles-ground-montage.png`, `tiles-ground-zoom.png` (2×, 8 biome rows),
`tiles-edges-montage.png`, `tiles-edges-zoom.png` (2×), `tiles-water-montage.png`,
`tiles-water-zoom.png` (3×), `tiles-patch-grass.png` / `-dirt` / `-stone` / `-edges` /
`-water.png` (6×6 iso composites), `tiles-transition.png`.

---

## 9. Not sourced / open items

* **No native Flare row exists for `grass_dry`, `sand`, `ash`, `moss`, `dirt_road`.**
  Those five are recolours of real Flare diamond rows (tint column in §3, same multiply
  mechanism the engine already used): dry grass ← grassland grass; sand and ash ←
  snowplains snow (warm-pale and cold-dark respectively); moss ← the 3× grassland grass
  row pushed green; packed-road ← `cave.png`'s gravel floor.  Only `grass`, `dirt`,
  `stone` map 1:1 onto an unmodified Flare row.
* The spec's pair list has **no `dirt|stone`** pair, so the transition demo uses
  `ash__stone` for the dirt→stone boundary (its neutral rim sits within 3 levels of both
  dirt and stone, so the seam numbers above still hold).  Add a 9th row to `EDGE_ROWS`
  and rebuild if a literal dirt→stone tile is wanted.
* `assets/flare/raw/tiles/grassland_water.png` y=32 (what `water_sources()` reads today)
  is a shoreline row — cliffs, docks, foam dashes — so it was deliberately not used.
* Vendor sheets under `vendor/flare-game/tiled/tilesheets/` are 3× the engine resolution
  (192×96 diamonds on a 16-column grid) and are downsampled 3:1 with premultiplied alpha.
* The neutral-rim caveat for `grass|sand` / `dirt|sand` is in §5.
