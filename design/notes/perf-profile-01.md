# perf-profile-01 — where the frame time actually goes

Method: `python -m cProfile -o design/notes/qa-01.prof -m emberfall.src.app
--qa --scene play --frames 900` (headless), then `pstats` sorted by cumulative
and tottime. 866 rendered frames in 175 s of profiled run time — absolute
numbers are inflated by the profiler, **shares** are what matters.

Raw data: `design/notes/qa-01.prof`, run log `design/notes/qa-01-profile-run.log`.

## Frame budget (share of the 175 s profiled run)

| area | cum time | share | verdict |
|---|---|---|---|
| `render.draw` | 114.9 s | **66 %** | the render path is the problem, not the sim |
| ├ `_draw_prop` (1,434,096 calls) | 64.9 s | 37 % | **1,656 prop draws per frame** — nothing is being culled |
| ├ `w2s` (3,462,271 calls) | 29.2 s | 17 % | ~4,000 world→screen conversions per frame |
| └ `_draw_fog` | 20.2 s | 12 % | per-pixel fog loop |
| `ui.draw → draw_hud → draw_minimap` | 20.6 s | 12 % | 5,422,892 `Surface.set_at` calls ≈ **6,260 per frame** — the minimap is being repainted pixel by pixel every frame |
| `world.update` | 37.1 s | 21 % | ├ `core.query` (129,983 calls) 26.7 s → ~150 spatial queries/frame |
| | | | └ `mapgen.height_at` (1,568,300 calls) 13.4 s → ~1,800/frame |
| `dict.get` (generic) | 13.0 s | 7 % | 7.67 M calls — hot dictionaries in the inner loops |

Measured in-game (qa-01 state, no profiler): **fps 44.8–54.6, mean ≈ 50 with
25 entities**. Target is 60 fps at 120+ units, so the render path has to lose
roughly two thirds of its work *before* waves land.

## Fix order (biggest share first)

1. **Cull props by camera rectangle before drawing.** `_draw_prop` is 37 % of
   runtime and is called 1,656×/frame while a 1600×900 view at 64×32 tiles
   shows at most a few hundred prop candidates. One `if not visible: continue`
   against the camera tile bounds (already computed for terrain) should remove
   most of it. Cache the visible-tile rect once per frame.
2. **Bake the minimap once.** 6,260 `set_at` per frame is the single worst
   API call pattern in the profile. Draw terrain to a static surface at map
   load, keep a fog layer that is only re-blitted when fog cells change, then
   one `blit` + the camera rect per frame. Expect the whole 12 % to collapse.
3. **Cut `w2s` traffic (17 %).** Compute each entity/prop→screen conversion
   once per frame and reuse it (pass the result down instead of recomputing
   inside `_draw_prop`, fog and sorting). `core.sx/sy/id` account for a further
   17.6 M calls at ~11.7 s combined.
4. **Fog as surfaces, not pixels.** `_draw_fog` at 12 % — render the veil into
   a cached 84×84 (or chunked) surface scaled up, instead of touching pixels.
5. **`height_at` → inline array index.** 1.57 M calls / 13.4 s for what is
   `m.height[y * m.w + x]`; a `__slots__`-free accessor or direct indexing in
   the hot loops removes most of it.
6. **Spatial queries (150/frame).** Check which systems query every tick:
   combat acquisition, gather reassessment and separation can all run at
   4–10 Hz staggered instead of every frame.

## Sanity check after the fixes

`python3 tools/qa/run_qa.py --label qa-02 --env state --cmd ".venv/bin/python
-m emberfall.src.app --qa --scene play --frames 3000 --shot ..."` and compare
the `fps` field against qa-01's mean ≈ 50 (same scene, same machine).
