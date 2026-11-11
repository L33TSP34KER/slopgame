# activities-suite-01 — PvE activity suite (council p-c4f1a9e2)

Lane: **deepseek**. Human directive (verbatim): *"the game is boring not enough
event thing to do. their is not a single camp farm. secret shop. im not saying
copy dota 2 but find other stuff because jusut farming posing building spawning
new army going to fight wait 10minute for necropolis to break. its long and
boring"*.

Build: staged commits on `feature/item-shop`, each gated, each carrying the
trailer `Council: p-c4f1a9e2`.

**Standing rule for this file: every number I invented is PROVISIONAL and is
offered to mimo's balance lane. I changed no necropolis HP, no wave cadence and
no difficulty tier.**

---

## Baseline (measured on a clean `git archive HEAD` copy, before any edit)

3000-frame soak, headless:

```
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy EMBERFALL_QA=state \
  .venv/bin/python -m emberfall.src.app --qa --scene play --frames 3000
```

| metric | baseline |
|---|---|
| mean fps (excl. first 10 state samples) | **61.27** |
| min / max instantaneous fps | 56.2 / 62.5 |
| state samples | 48 (one per sim second) |

Same command is re-run at the final stage; the gate is **final within 3 of
baseline**. Gate numbers at every stage: `tools/qa/release_check.py` must stay
**0 FAIL / 0 WARN / 44 checks** (baseline confirmed: 0/0/44 on clean HEAD).

---

## STAGE 1 — respawning tiered camps + ancient mini-boss

### Mechanics (file:line)

| mechanic | where |
|---|---|
| camp `tier` field on every camp dict | `emberfall/src/mapgen.py:655` (`camp(tier=...)`, stored `mapgen.py:665`) |
| tiered placement: 4 warrens + 2 medium camps + 1 ancient lair, scale-aware `X()/Y()` | `emberfall/src/mapgen.py:698-714` |
| ancient anchor is a 4-tile clearing with its own dressing | `emberfall/src/mapgen.py:711` (`clear_r=4`) |
| mission-1 trim: 2 warrens + 1 weak camp, NO ancient | `emberfall/src/campaign.py:347-365` (`_shape_camps`, called `campaign.py:409`) |
| roster ladder by mission index (PROVISIONAL) | `emberfall/src/campaign.py:330` (`_camp_roster`) |
| Ashen Colossus unit (neutral, boss, HP 2600) | `emberfall/src/defs.py:201` |
| respawn timers + clear bonuses + neutral cap (PROVISIONAL) | `emberfall/src/defs.py:366-374` |
| relic items (grant-only, not in any shop tree) | `emberfall/src/defs.py:456,462` |
| clear bonus + respawn scheduling in `check_camp` | `emberfall/src/world.py:1433` |
| respawn tick (cap-aware, toast, vfx) | `emberfall/src/world.py:1467`, ticked from `world.py:1639` (`update_mission`) |
| relic grant / gold fallback | `emberfall/src/world.py:1506`, drop hook `world.py:1524` (called from `kill`) |
| additive vfx cue | `emberfall/src/vfx.py:366` (`spawn_camp_glow`) |

### Design notes

* Respawn is **pure `camp_cleared` bookkeeping**: the camp dict and anchors
  never move; units are re-spawned from the stored roster at the stored anchor
  with `u.home`/`u.camp` re-set exactly like `_spawn_start` does.
* Camp-clear gold is credited **only** to a PLAYER killing blow (per brief);
  respawn scheduling happens on any clear so a camp emptied by the Host still
  re-stirs.
* Live neutral pool is capped at `NEUTRAL_LIVE_CAP = 40`; when the pool is full
  the respawn is **postponed** by 15 s, never dropped (perf guard).
* Art for the ancient is a **rig reuse** (`rig="hollow-king"`, NEUTRAL team
  tint — `defs.py:203`). Verified while building: `render._draw_unit` keys
  purely off `e.rig` + `e.team`, and `Entity.scale` is **never read by any
  renderer** (`grep '\.scale' render.py/ui.py/app.py` → only prop scale and
  `pygame.transform` calls), so a "scaled goblin-brute" would have been
  pixel-identical to a normal brute. The king rig's own `UNIT_SCALE` (1.76)
  carries the size story instead. Boss bars: none exist render-side today
  (`render.py:1049` draws a plain bar when `hp < max_hp`), so the ancient shows
  the standard bar as soon as it takes damage.

### Anchor selection (evidence)

New anchors were picked by a grid search (step 3 over base coords 8..78) scored
against **all ten layouts** (classic 84x84 + the nine campaign seeds/sizes/
flips): flat ground (height 1, no water within a 2-tile disc), ≥5 from every
mine/camp/start footprint in every variant, reachable from the player spawn
under mapgen's own carve rules. Survivors were then checked by
`tools/qa/map_audit.py --json` on the default map.

Chosen: **Ashenfield Camp (56,53)**, **Kingsroad Camp (62,29)**,
**Ashen Barrow (44,23)** — all `X()/Y()` scaled, so 96..128 maps keep the
same proportions.

### Mission-1 contract verification (p-7b4e55d1)

* Composition measured: `m1 camps: Crossroads Warren(2) + Mesa Warren(4) +
  Ashenfield Camp(3, no brute) = 9 neutrals`, **0 ancient**, 0 ENEMY bosses.
  (≤2 warren-tier + 1 weak camp — the "2 warrens + 1 weak camp" rule; the
  Stage-4 probe asserts exactly this.)
* "Neutrals never leave their home radius" — **verified empirically, with a
  caveat I will not paper over**: `u.home` is written at `world.py:151` and
  never read anywhere in the engine, so there is no hard leash today. Measured
  behaviour: a camp goblin aggroes a footman that walks into its 8-tile sight,
  and when the footman is teleported 20 tiles away the goblin *pursues* —
  5.32 tiles from home after 20 s (it never teleports, never paths fast, and
  never wanders off unprovoked; aggro is sight-gated). On mission 1 the
  nearest camp is ~19 tiles from the Hall and player **attack-move ignores
  neutrals** (`world.py:919` filters `team=ENEMY`), so nothing on m1 reaches
  the hall on its own — consistent with the autoplay win below. I did **not**
  add a leash: that would be a behaviour change to an existing system, which
  my brief forbids. Filed here as a candidate knob for mimo instead.

### Stage 1 gates

| gate | result |
|---|---|
| `tools/qa/release_check.py` | **0 FAIL / 0 WARN / 44 checks** |
| `tools/qa/map_audit.py --json` | **PASS**, 0 findings (15 key points, all reachable, both bases reach all) |
| `tools/campaign_probe.py --no-win` | **ALL PASS** (9-matrix + m1 contract + progression) |
| smoke: clear → respawn cycle, relic keep/fallback | pass (see probe matrix, Stage 4) |
