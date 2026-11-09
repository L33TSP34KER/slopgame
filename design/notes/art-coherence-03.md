# art-coherence-03 — first in-scene review (Flare units + current terrain)

Rendered by mimo with `tools/qa/scene_shots.py` (runs the engine's own
`tools/scene_test.py` unmodified, redirects its saves into
`design/notes/shots/`), so these are true engine frames, not mockups:

- `design/notes/shots/scene-scene-player.png`
- `design/notes/shots/scene-scene-enemy.png`
- `design/notes/shots/scene-scene-mine.png`

## Verdict

The Flare unit swap is a **big win** — painted, readable, correctly grounded
with soft shadows, faction split (warm humans vs cold undead) still instant.
The map composition reads like a real RTS. But there are **seven visible
render artifacts** that make it look unfinished, and the procedural buildings
now clash hard with the painted units.

## Blockers (visible in ≥2 of the 3 frames)

1. **Giant pale-yellow ellipse** sitting on the ground beside the town hall
   (player + mine frames). Flat cream fill, no texture, clearly not intended —
   looks like a placement/rally/mine-glow sprite drawn at the wrong scale.
2. **Hard-edged translucent overlay quads.** Each frame has one or more
   large semi-transparent dark rectangles with visible straight boundaries
   (left band in player frame, corners in mine/enemy frames). This is a
   light/fog/vignette pass being drawn with wrong extents — it is the single
   most "unfinished" thing on screen. A vignette must be feathered, a fog pass
   must be tile-aligned.
3. **Water reads as a debug grid.** Every water diamond shows its own outline,
   there are two different cyans in the same river (deep teal vs bright
   turquoise), and ford tiles are outlined in orange. Result: the river looks
   like a placeholder tile tester. Needs one water shade, seams blended (draw
   adjacent-tile edges only on biome boundaries), fords as shallow tint +
   stepping stones.
4. **Campfires render as bright orange traffic cones** (enemy + mine frames,
   several of them). A campfire should be a dark stone ring with a small warm
   glow, not a saturated orange triangle — right now they are the loudest
   pixels on the map and they mark creep camps.

## Should-fix before beta

5. **Procedural buildings vs painted units.** Grey boxes with maroon roofs
   next to Flare-painted knights is now the biggest style seam in the game
   (my `assets/flare/buildings/` crops are landing to replace them).
6. **Ash plateau = grey checker.** The desaturation fix worked, but the enemy
   plateau currently reads as a gravel car park: it needs cracked-earth
   variation, bone/scatter props and a violet cast at the edges so it says
   "blighted ground".
7. **No contact shadows under buildings** — units and trees cast soft shadows,
   buildings sit flat on the ground and look pasted. Same shadow recipe, done.
8. **Thin black line artifact** along the ramp/cliff edge in the enemy frame
   (runs from ~(480,520) to (1130,600)) — a seam between wall/cliff segments.

## Confirmed fixed / good

- The `art.py` stone-prop crash no longer reproduces (raw run of
  `tools/scene_test.py` completes; thanks — retracting my nag).
- Unit grounding, shadows, and scale vs buildings are sane.
- Trees: three tonal variants read, rim light helps, forests no longer a blob.
- Fog/night floor is much better than pass #1.

## How I'll verify the fixes

`python3 tools/qa/scene_shots.py` → same three frames → I diff visually and
update this note. Once the game entry lands, the same frames come from
`tools/qa/run_qa.py` at real gameplay moments (base, combat, night).
