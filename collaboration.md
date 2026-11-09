# collaboration.md — mimo ⇄ deepseek (live coordination log)

> User directive (2026-11-09, 00:47): *"use the broadcast system to work with
> another agent… work with deepseek… figure out with mimo who does what and
> keep looping… 8 hours… ready for release at least beta."*
> This file is maintained by **mimo** and is read-only for everyone else.
> Deepseek's contract (`design/COLLAB.md`, `design/DESIGN.md`,
> `design/ASSET-CONTRACT.md`) stays authoritative for code ownership; this log
> records what we agreed, when, and what happens next.

## Channel

| | |
|---|---|
| Broker | `127.0.0.1:8770` (broker.py protocol, already running) |
| Durable log | `design/bus/messages.jsonl` |
| Send | `python3 bus.py send --from mimo --to deepseek --text "..."` |
| Watch | `python3 bus.py watch --name mimo` (mimo also keeps `comms/` listener) |
| Cadence | both agents poll the bus every few minutes; every decision lands here |

## Rules from the user (relayed over the bus, both sides confirmed)

1. **ONE game** (01:07) — no second title; every minute goes into Emberfall.
2. **Always headless** (01:04) — `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy`;
   no visible windows; QA goes through the game's own hooks
   (`EMBERFALL_QA=1`, state JSON, `--shot`/`--script`, `pygame.image.save`);
   Xvfb/screen-grab is fallback only.
3. **AAA bar** (01:12) — if we think we're finished before 08:00, the question
   is "is the game triple-A?" — if not, we are not finished. Continuous polish.
4. **Discord status channel** — `comms/discord.py` posts milestones to the
   user's webhook (also `tools/notify.sh` on deepseek's side).
5. **Art reset** (01:19, relayed) — procedural art is unacceptable; switch to
   the **Flare** open-source isometric set (CC-BY-SA 3.0, Clint Bellanger +
   Flare contributors). mimo owns the extraction pipeline:
   `vendor/flare-game` (cloned), `tools/flare_buildings.py`,
   `assets/flare/buildings/`, `design/notes/flare-import.md`,
   `design/notes/flare-buildings.md`, `LICENSES-FLARE.md`.

## Who does what (agreed 00:52–00:55)

| area | owner | notes |
|---|---|---|
| engine + gameplay code | **deepseek** | `emberfall/` (native), `prototype-web/` parked, README, `design/*.md`, `tools/` |
| audio (SFX + music) | **mimo** | `assets/audio/**` per `design/ASSET-CONTRACT.md`, synthesized, loudness-gated |
| art / icons | **deepseek** | `assets/icons/`, `assets/art/` optional touches by mimo only if agreed on bus |
| QA harness + bug notes | **mimo** | `tools/qa/`, `design/notes/qa-NN.md` |
| map critique, lore, balance | **mimo** | `design/notes/` |
| second game (user asked for 2) | ~~mimo~~ | **CANCELLED 01:07 — user corrected to one game** |

Rule: never edit a path you don't own — propose it on the bus instead.
Ultimate decision power for scope/tech/quality calls: **mimo** (per user).

## Stack decision

- 00:53 — deepseek reported the user rejected web tech → **native desktop**,
  Python 3 + **pygame-ce** (`.venv/`), 1600×900 window, Linux beta binary.
  Verified on disk by mimo: `.venv/lib/.../pygame_ce`, `emberfall/`,
  `prototype-web/` (parked web prototype), `design/native-test.png`.
- QA accordingly: Xvfb + PIL/ffmpeg screenshots, no Chromium.
- Design lock unchanged: `design/DESIGN.md` — Emberhold humans vs Hollow
  Host undead, hero Marshal Aldric, one 84×84 map "Ashen Vale", WC3-like.

## Status timeline (mimo's side)

- 00:47 — user brief received; goal armed for the 8 h window.
- 00:51 — mimo online on the hub; handshake with deepseek completed.
- 00:52 — deepseek contract read; ownership table accepted.
- 00:53 — pivot to native pygame confirmed on disk; QA approach switched.
- 00:55 — music direction answered (choir+bone-percussion marching spine for
  battle, dying-embers cello for menu); audio pack v1 ETA +30 min.
- 00:55 — audio pack subagent launched (21 SFX + 3 music loops, synthesis →
  OGG with peak/RMS/loop verification).
- 00:55 — this file created per user instruction.
- 01:01 — **map critique #1** (`design/notes/map-critique-01.md`): keep the
  single plateau ramp as main approach but widen to 4 tiles + add a
  non-buildable soft crossing; add south-central mine (44,54); make fords
  readable; move the SE camp off its mine; add a BFS map self-test.
  Deepseek acted on all of them (goat path x=73..75 y=24..29, Crossroads Pack
  (48,58), camp → (74,63)) and corrected my tile coords (preview pad offset).
- 01:02 — **art coherence #1** (`design/notes/art-coherence-01.md`): icon
  sheet excellent; terrain/icon seam; fog-as-black-circles (was merged tree
  shadows — fixed); night too dark; grass checker too regular; ink edges on
  props. Deepseek confirmed all five + font licensing (C059 GPL+FE, DejaVu).
- 01:07 — user correction relayed: **one game only**, no game2.
- 01:08 — **QA harness v1 self-tested** (`tools/qa/run_qa.py` →
  `design/notes/selftest2.md`): state-JSON stream, cadence probe, screenshots,
  traceback detection. Xvfb path fixed (`-extension GLX`), then default moved
  to headless per the user rule.
- 01:12 — user rule relayed: **AAA bar** — finishing early means it isn't
  finished.
- 01:14 — Discord ops channel live (`comms/discord.py`, 204 OK).
- 01:15 — **audio tranche 1 landed, independently verified** (8 SFX):
  ffprobe + `pygame.mixer.Sound()` both pass, durations exact,
  RMS −19…−24 dBFS, no clipping.
- 01:17 — **map audit run 1 = FAIL** (`tools/qa/map_audit.py`):
  Thornwood Pack camp unreachable (dead content), 11 unreachable pockets ≥3
  tiles; crossings, fairness, build space, wood parity all PASS.
  Report: `design/notes/map-audit-01.md`.
- 01:19 — bug reported: `emberfall/src/art.py:340` `_make_prop` draws the
  `stone` branch before `s = new_sprite(...)` → `UnboundLocalError`, crashes
  `tools/scene_test.py` (blocks in-scene art review).
- 01:19 — **art reset**: procedural art rejected → Flare set (CC-BY-SA 3.0).
  Cloned `vendor/flare-game` (shallow+sparse, 1.3 GB); extraction pipeline and
  import doc started; `LICENSES-FLARE.md` required before release.
- 01:30 — all 23 audio files on disk; my review found music spec misses
  (battle 73.6 s < 90 s, RMS −16.7 over −18, peak −0.53) + DC offsets in 4
  SFX → fixes ordered; montage `design/notes/audio-review.png`.
- 01:38 — **in-scene art pass 03** with `tools/qa/scene_shots.py` (runs the
  engine's own scene test through a shim): 8 issues filed — yellow-ellipse
  artifact, hard-edged overlay quads, debug-grid water, orange campfire cones,
  procedural-vs-Flare building seam, flat ash, missing building shadows,
  cliff seam line. `design/notes/art-coherence-03.md`. Stone crash confirmed
  fixed (nag retracted).
- 01:45 — receipt ping sent; deepseek's watcher is alive (durable log shows
  my messages being appended by its side) but its last post is 01:19 — it is
  heads-down on `world.py`/sim.
- 01:47 — entry probe: `python -m emberfall.main` → *No module named* yet.
  Declared hooks: `EMBERFALL_QA=1` (fixed seed, skip title, scripted battle),
  `EMBERFALL_QA=state` (1 JSON line/sec), `--shot PATH --shot-at FRAMES`.
- 01:50 — **release gate**: `tools/qa/release_check.py --gate beta`, 41 checks,
  baseline **8 FAIL / 3 WARN** (my Flare outputs in flight, README run
  instructions, CC-BY-SA licence file, map reachability blocker).
  Report: `design/notes/release-check.md`.
- 02:02 — map blocker **fully diagnosed**: Thornwood Warren sits in a 3-tile
  pocket walled by trees (cols x=73/75, rows y=60/64); its only contact with
  the main map is a diagonal rejected by the corner rule. One-tile fix sent on
  the bus: unblock trees inside the camp clearing (radius 2), like the start
  building footprint logic.
- 02:07 — `design/notes/flare-import.md` landed (522 lines): frame format
  verified (8 fields + optional 9th image-ID), every sheet has 8 directions,
  numbering **0=SW 1=W 2=NW 3=N 4=NE 5=E 6=SE 7=S**, layer order varies by
  direction (`hero_layers.txt`), anchor = `blit at ground − (ox, oy)`, enemy
  mapping table, **no wolf/quadruped sprite exists in any Flare mod**.
  Two engine bugs found in it: direction table 45° off, anchor jitter.
- 02:10 — **the game boots**: all 8 scenes swept headless; only `battle`
  crashes (`render.py:412`, particles are dicts). Shots in
  `design/notes/shots/scene-*.png`.
- 02:18 — **qa-01 published** (`design/notes/qa-01.md`): 65 s run, rc=0, no
  traceback, 1 Hz state stream, scored against the 11-section checklist.
  FAILs: fps mean ≈ 50 @ 25 entities, food `[28,16]` over cap, hero ability
  icons missing (since fixed by deepseek), map audit, README.
- 02:24 — **perf profile** (`design/notes/perf-profile-01.md`): render = 66 %
  of frame time — `_draw_prop` 37 % (1,656 draws/frame, no camera culling),
  `draw_minimap` 12 % (6,260 `set_at`/frame), `w2s` 17 %, `_draw_fog` 12 %,
  `height_at` 1.57 M calls. Fix order written up.
- 02:26 — **audio closed**: 23/23 files green on both my gates and the
  generator's own verifier (battle rebuilt to 114.3 s with a real arc, SFX
  family spread 2.45 dB, loop seams ≤11 % of interior peak).
- 02:30 — **14 Flare building crops + catalog + licence landed**; montage
  reviewed (`art-coherence-04.md`): 4 strong, 5 weak — prop piles, keep vs
  temple identical, Necropolis reads as a graveyard corner, no faction colour.
  Upgrade pass launched; release gate now **3 FAIL** (README, map ×2).
- 02:41 — soak test (speed 4, no input): wave 1 at t≈246, wave 2 at t≈389,
  army drained 16→0 by t=431 while buildings held — AI pressure verified.
  An unreproduced fps collapse (61 → 0.7) filed with suspects.
- 02:57 — **deepseek replies after 1h45m**: beta runnable, run line frozen
  (`./play.sh` / `.venv/bin/python -m emberfall.main`), `--autoplay` added, my
  crops integrated; asks for qa-02 on HEAD + "the ugliest thing fixable in 20 min".
- 03:16 — commits **Milestone 3: playable beta** and **Beta polish** (fords,
  alerts, fog veil, control groups, HUD centre panel).
- 03:18 — **build-menu blocker found by my controls probe** (action kind
  `buildmenu` had no `handle_action` branch → B and the HUD button were dead).
  Fixed by deepseek within ~20 minutes.
- 03:35 — **controls probe 18/18 PASS** on HEAD (`design/notes/qa-input-01.md`).
- 03:18 — **qa-02 launched** on HEAD (`--autoplay --speed 3 --frames 12000`).
- 03:33 — **the late-game freeze is reproduced deterministically**: fps 60 →
  40s in wave 2 → cliff at t=524 (51→14→2.4) → **0.8 fps** by t=568 with only
  ~36 entities; same signature as the 02:41 soak. Profile at t=420 shows the
  cost is sim-side, not render: `World.enemies_near` ~95 calls/frame and
  `SpatialHash.query` ~188 calls/frame (37 % + 35 % of profiled time) with
  `find_path` 99 calls/60 frames — per-unit enemy acquisition every tick =
  O(units²). Fix direction sent: stagger acquisition to 4–10 Hz, cache results,
  skip units that already have a target.
- 03:38 — bisect harness `design/notes/repro_freeze_split.py` running to split
  update-time vs draw-time through the collapse.
- 03:40 — **deepseek fixed the freeze first** (commit `ea1a0a1`: A* path budget
  + repath cooldowns while sieging, building acquisition/reach, spawn scatter,
  building scales). My bisect on that HEAD **confirms it**: t=978, 106
  enemies, 74–93 fps (update 1–3 ms, draw ~10 ms).
- 03:47 — **qa-02 published** (`design/notes/qa-02.md`). Verified fixed: build
  menu (controls 18/18), freeze, food cap. Open: **stalemate/no end-state**
  (3 player units vs 106 enemies, `state=play` for 16 in-game minutes),
  unbounded enemy growth (29→106), wave-spawn A* hitch (~22k `can_step` in
  one block → 26–29 fps for half a second), siege conversion too slow
  (Necropolis −19 HP/s, army trickles in one unit at a time), no building
  growth after minute 1 of autoplay.
- 03:52 — building-upgrade subagent: 90 min of toolchain, no PNG rewritten
  yet; proceeding necropolis → keep → temple → ziggurat → rest, landing
  incrementally, hard stop 04:45 for necropolis+keep, 05:15 overall.

- 04:08 — **boot regression caught live**: `mapgen.py` line 522 appended to
  `m.problems` one line before it was assigned → every launch crashed. Reported
  with the exact line; fixed within minutes, boot re-verified green.
- 04:12 — **RELEASE GATE GREEN**: `release_check.py --boot` → 0 FAIL / 0 WARN
  across 39 checks (audio, icons, crops, licence, README cold-test, docs,
  map audit PASS with 0 findings after the Thornwood + pocket fixes).
- 04:14 — **feature audit 31/31** (`design/notes/feature-audit-01.md`):
  DESIGN.md promises all present — rosters, abilities, upgrades, difficulties,
  fog/day-night, controls, victory/defeat, credits attribution, 20/20 SFX
  wired, lore copy in-engine.
- 04:36 — deepseek lands all **qa-02 fixes**: enemy production capped at 50,
  wave spawns staggered (~1 unit/0.2 s), hall-loss defeat, repath-timer bug,
  array-based A* (115-unit stress 48→77 fps), water lattice removed (it was
  the per-tile dash animation), torn barracks crop replaced. Assigns mimo the
  **PyInstaller artifact** (`dist/Emberfall`).
- 04:43 — **v2 crops 1/2 verified** (keep + necropolis): silhouettes pass the
  48 px name test and 200 px draw-width test; material defect filed — stone
  reads glassy (diamond lattice seams + low plane contrast; alpha measured
  98.3 % opaque, so it is painting not transparency).
- 04:52 — **qa-03: 3/3 PASS** — hall-loss → defeat in 0.4 s; siege autoplay →
  victory (Necropolis 5200 → 0 by t=180); torn sprite gone, water fixed.
- 04:55 — **release artifact built**: `dist/Emberfall/Emberfall` (onedir,
  83 MB) — first attempt bundled the broadcast demo's `main.py` (name
  collision), fixed with `packaging/frozen_entry.py`; verified headless across
  base/title/battle/victory/siege, zero tracebacks.

## Open items / next loop

- [x] audio pack — 20 SFX + 3 music, all gates green (closed 02:26)
- [x] `design/notes/flare-import.md` (frame format, directions, layers, enemy mapping)
- [x] `tools/qa/` harness + scene sweep + qa-01 + perf profile + release gate
- [x] 14 Flare building crops + catalog + `LICENSES-FLARE.md`
- [ ] deepseek: canonical run line (`-m emberfall.main` shim vs `-m emberfall.src.app`)
- [ ] deepseek: particles crash (`render.py:412`) → unlocks combat QA
- [ ] deepseek: Thornwood camp tree-corner fix → mimo re-runs `map_audit.py`
- [ ] deepseek: README run instructions (release blocker, deepseek owns README)
- [ ] deepseek: perf fixes in order — prop culling, minimap bake, w2s, fog, height_at, query staggering
- [ ] deepseek: scripted-input QA hook (`--script` or auto-play) → unlocks checklist sections 2/3/4/5
- [ ] mimo: building upgrade pass review (montage + 48 px naming test) — subagent running
- [ ] mimo: qa-02 once combat + perf + map fixes land; art-coherence #5 on the wired result
- [ ] mimo: packaging check (pyinstaller binary) + cold-test README instructions
- [ ] both: polish loop until 08:00 (AAA bar)

## Decision log

| time | decision | who |
|---|---|---|
| 00:52 | one shared workspace, `emberfall/` = deepseek code, no edits from mimo | both |
| 00:53 | native pygame-ce desktop instead of web | deepseek (user-reported), mimo verified |
| 00:54 | mimo maintains top-level `collaboration.md` (user directive) | mimo |
| 00:55 | battle music = bone percussion + male choir spine w/ cold string swells | mimo (asked by deepseek) |
| 01:07 | one game only — second title cancelled | user (relayed), both confirmed |
| 01:04 | always headless: SDL dummy drivers, game-side hooks for QA | user (relayed), both confirmed |
| 01:12 | AAA bar: "finished early" = not finished; polish until 08:00 | user (relayed) |
| 01:17 | QA gate = `tools/qa/map_audit.py` + `tools/qa/run_qa.py` reports in `design/notes/` | mimo |
| 01:19 | art direction reset to Flare CC-BY-SA 3.0 set; extraction owned by mimo | user (relayed), both confirmed |
| 01:20 | vendor drop: `vendor/flare-game` (1.3 GB sparse clone) committed to workspace, not git | mimo |
