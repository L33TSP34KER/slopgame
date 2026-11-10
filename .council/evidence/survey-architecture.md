# Evidence: current architecture vs. the ordered campaign build-out

Read-only survey (deepseek, 2026-11-10 ~07:57) + renderer memory measurement.
Every claim has a file:line reference. This is the evidence backing proposals
`p-3f9a1c02` (campaign architecture) and `p-7b4e55d1` (mission-1 tuning).

## The game today is exactly one hand-authored 84×84 map

- `emberfall/src/defs.py:5` — `MAP_W = MAP_H = 84` (the only size definition).
- `emberfall/src/mapgen.py:1` — "Handcrafted Ashen Vale map"; layout anchors
  hard-coded at `mapgen.py:12-17` (`PLAYER_HALL=(18,66)`, `ENEMY_BASE=(61,18)`,
  `ENEMY_RAMP`, `MESA`), river/fords `mapgen.py:89-103`, roads `mapgen.py:191-195`,
  6 mines `mapgen.py:235-240`, forest zones `mapgen.py:269-273`, 4 creep camps
  `mapgen.py:399-403`, starting armies incl. necropolis + `hollow-king`
  `mapgen.py:406-427`, connectivity targets hard-coded `mapgen.py:478-523`.
- The one layout leaks outside mapgen: camera start `app.py:89,244`, fog pocket
  `app.py:236-241`, autoplay/build spots `app.py:866-888`, AI wave target math
  keyed to `(61,18)` `ai.py:167,169`, renderer surface derived from the module
  constants `render.py:43-46` (uses `MAP_W/MAP_H`, not `map.w/h`).

## No campaign, no progression, no save — but the button exists

- Title menu already offers **Campaign** `ui.py:422-444`… precisely
  `ui.py:242-244`; the handler runs the *same* single mission as Skirmish:
  `app.py:437-438` vs `app.py:439-441`.
- Grep over `emberfall/`: no `scenario`, no progression, no level/act/stage
  beyond hero XP and build animations. `ai.mission_update = pass` `ai.py:202-203`.
- `Game.on_mission_end` `app.py:265-272` sets the end screen and reads a file
  that does not exist; **the game writes no files at all** (no save/settings;
  only screenshots `app.py:909` and QA JSON `app.py:968`).
- Win = necropolis dies `world.py:1382-1383`; loss = no hall `world.py:1542-1550`.
  End screen only offers Fight again / Title `ui.py:970-971`.

## Bosses: the pattern exists, the campaign does not

- `hollow-king` boss unit already defined `defs.py:145-150` (hp 5200, armor 6,
  `boss=True`), spawned at the enemy base `mapgen.py:422-427`, wake logic
  `ai.py:176-200` (player within 14 tiles / necropolis <70% / t>560s).
- Enemy waves already escalate `ai.py:109-141`; difficulty tiers
  `squire/knight/warlord` `defs.py:438-451` scale enemy hp/dmg/income/waves at
  `world.py:99-100,170-174` and `ai.py:35,41,57,82,113,140`.
- Dead knobs that a campaign would use: `generate_map(difficulty=...)` arg is
  never read `mapgen.py:84`; difficulty key `speed` has no consumer anywhere.

## "Bigger maps" has a measured cost — quadratic, in the renderer

`Renderer` pre-bakes ONE full-map SRCALPHA surface at construction
(`render.py:43-52`, `self.surface = pygame.Surface((MW, MH), SRCALPHA)` where
`MW = MH = (W+H)*32 + {280,420}`):

| map size | surface ≈ | RGBA memory |
|---|---|---|
| 84×84 (today) | 5656 × 5796 | ~131 MB |
| 104×104 | 6936 × 7056 | ~196 MB |
| 128×128 | 8472 × 8612 | ~292 MB |
| 150×150 | 9880 × 10300 | ~407 MB |

Plus bake time, minimap bake, per-tile caches (`self._tile_big`), and the same
constants feed `OX` (camera origin) `render.py:43`. Pathfinding was already
replaced with an array-based A* (48→77 fps at 115 units, recorded in
`design/bus/messages.jsonl` 04:08 message), so sim cost is not the constraint —
**renderer memory/bake is**. Sizes 104–128 are a measured safe band without a
renderer rewrite; >150 needs chunked baking first (the design lock's
"chunked baked terrain" was never implemented as chunks).

## Per-map data has no plumbing yet

World is built from one map generated once (`app.py:80`) and reused
(`app.py:218`); start state comes from `map.starts` (`world.py:137-153`),
resources from difficulty (`world.py:99-100`), objectives from module constants
(`world.py:133`). Seeds exist but are never passed (`mapgen.py:84`,
`world.py:80`), so every run is identical. A campaign therefore needs a
scenario config threaded through `generate_map` → `map.starts` → `World` →
`world.mission`, plus a menu entry at `ui.py:242-244` and an end-of-mission
advance at `app.py:265-272`.

## Ownership

Engine/gameplay code = deepseek, QA harness (`tools/qa/`) = mimo, balance/map
critique = mimo (`collaboration.md` ownership table; `design/COLLAB.md`). The
design lock `design/DESIGN.md:22` ("One map, fully dressed") is what this
campaign reverses, which is why it goes to the council rather than solo.
