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

---

## STAGE 2 — the secret shop (Wayfarer's Exchange)

### Mechanics (file:line)

| mechanic | where |
|---|---|
| neutral structure (HP 1500, 3x3, NEUTRAL) | `emberfall/src/defs.py:330` |
| 180 s rebuild timer + reach radius | `emberfall/src/defs.py:385,388` |
| 5 exclusive items (`secret=True`, no recipe tree) | `emberfall/src/defs.py:485-515` |
| secret stock groups (panel shelves) | `emberfall/src/defs.py:533` |
| scale-aware placement (base 45,12 → `X()/Y()`) + footprint opened pre-sealing | `emberfall/src/mapgen.py:732` |
| mirror rule for flipped campaign maps | `emberfall/src/mapgen.py:287` |
| spawned NEUTRAL at world start | `emberfall/src/world.py:168` |
| reach check (same shape as the Purveyor) | `emberfall/src/world.py:572` |
| counter chooser used by UI + buy routing | `emberfall/src/world.py:584` |
| secret-vs-purveyor reach routing inside `buy_item` | `emberfall/src/world.py:668` |
| destroy → toast + 180 s rebuild schedule | `emberfall/src/world.py:1447` (kill), `world.py:1553` (tick; never overwrites a live footprint) |
| Merchant's Tithe income tick (integer accumulator) | `emberfall/src/world.py:1583` |
| panel: title, sub-line, stock list, out-of-reach advice switch on the counter | `emberfall/src/ui.py:1151-1152,1160` |
| selectable structure gets an "Exchange [P]" command | `emberfall/src/ui.py:1272` |
| art: existing Flare crop, zero new extraction | `emberfall/src/flare_buildings.py:34,188` |

### Art + licence status

`assets/flare/buildings/` has **no** market/tent/cart crop (contents: 8 human
buildings + 6 undead ruins). The closest already-attributed fit for a *hut*
is `human_house_farm.png` (log cabin with a banner), catalogued under the new
id at `flare_buildings.py:34` with a warm trade tint (1.0, 0.9, 0.74) and a
purpose-drawn `_fx` dressing at `flare_buildings.py:188` — lantern glow over
the door, hanging coin sign on a post, two crates on the porch — so it never
reads as the player's farm (which gets crop rows instead).

**LICENSES flag status: none needed, none sent.** No new crop was extracted,
`tools/flare_buildings.py` and `LICENSES-FLARE.md` were not touched, and the
licence gate still reports attribution complete (release_check `license:flare`
PASS).

### Exclusive stock (PROVISIONAL — mimo's balance lane)

| item | cost | stats / active |
|---|---|---|
| Waystone Shard | 850 | +70 mana, **active blink 9 tiles / 26 s** |
| Bulwark of the Old Road | 1050 | +9 armor, +340 hp, +3 hp/s |
| Merchant's Tithe | 1150 | +120 hp, **+1.2 gold/s** |
| Ashen Warpike | 1250 | +34 dmg, +15 % attack speed |
| Lantern of Long Roads | 750 | +4 sight, +12 % move, +2 hp/s |

Priced against the ~1600 g masterwork trees as slot-efficient one-item
purchases; none of them is in `SHOP_GROUPS` or `AUTO_SHOP_ORDER`, so the
Purveyor never sells them. Icons re-use existing `assets/icons` keys
(`it-ashenstep`, `it-bulwark`, `gold`, `it-warbrand`, `it-flask`) — assets are
read-only for this lane, so no new icon files were added.

### Anchor evidence

Grid-searched the 3x3 footprint on all ten layouts: flat ground, ≥4 from every
start footprint, ≥6 from every mine/camp, reachable from the player spawn, and
**blocking the footprint must not sever any key point** (flood re-run with the
3x3 blocked). 35 candidates survived all maps; the shipped one is base
**(45, 12)** — north-centre, enemy side of the map, ~60 tiles from the Emberhold
hall (the trip *is* the risk).

### Stage 2 gates

| gate | result |
|---|---|
| `tools/qa/release_check.py` | **0 FAIL / 0 WARN / 44 checks** |
| `tools/campaign_probe.py --no-win` | **ALL PASS** |
| smoke (9 maps spawn the Exchange, reach/buy/sell/refuse, destroy→rebuild, tithe, both panel modes draw) | pass |
