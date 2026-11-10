# EMBERFALL — The Hollow Crown

A native isometric real-time strategy game. **No web technology.** Python 3 +
pygame-ce, 1600×900, handcrafted 84×84 map, painterly Flare art, fully headless-testable.

> *The crown is broken. The king beneath it is not.*
> You are Marshal Aldric, last Ember of the Emberhold. Raise a keep, wake the vale,
> and break the Necropolis before the Hollow Host drowns it.

## Play

```bash
./play.sh
# or the packaged Linux build:
dist/Emberfall/Emberfall
```

First run creates a local `.venv` and installs `pygame-ce` (network required once).
If a venv already exists: `.venv/bin/python -m emberfall.main`.

Useful flags:

```bash
./play.sh --difficulty novice      # novice / squire / knight / warlord
./play.sh --music 0.35 --sfx 0.8   # mixer volumes
./play.sh --autoplay               # let the marshal play himself (QA/demo)
```

## Controls

| Input | Action |
|---|---|
| Right-click | Move · attack · gather · set rally |
| Left-click / drag | Select · box-select · Shift adds · double-click selects type |
| `A` | Attack-move (click a point) |
| `S` / `H` | Stop / hold position |
| `B` | Build menu (workers), then pick a structure |
| `P` | Purveyor: buy components, forge items, sell (hero near Hall/Keep/Altar) |
| Click satchel slot / right-click | Use an active item / sell it for 50% |
| `Q W E R` | Hero abilities: Ember Lance · Aegis · Consecrate · Daybreak |
| `1–9` / `Ctrl+1–9` | Recall / assign control group |
| `Space` / `F1` | Center on Aldric / idle worker |
| `O` / `Esc` / `F11` | Objectives / pause / fullscreen |
| Arrow keys / screen edge / middle-drag | Camera |

## What is in the beta

- **Campaign: nine missions, one crown** (`Campaign` on the title). Every map is
  bigger than the classic 84×84 Ashen Vale (96² → 128², capped at 128 by
  council decision `p-3f9a1c02`), each with its own layout flip, difficulty tier,
  objectives and briefing — and a **boss on every mission from 2 to 9**
  (Grave Warden → Crypt Herald → Bone Tyrant → Ash Lich → Slaughter King →
  Frost Sovereign → Hollow Champion → the Hollow King). Missions unlock in
  order and progress saves to `~/.emberfall/campaign.json`.
- **Mission 1 is a tutorial walk** by design: Novice tier (first wave at 10:00,
  enemy at 40% strength), no boss, two guards, a 3200-HP Necropolis — council
  `p-7b4e55d1` after the human reported the first map "actually impossible".
  That same decision fixed the two bugs that made it so: the hero now revives
  at the Hall without an Altar, and enemy waves fire on schedule instead of
  only while you stay away from the Necropolis.
- Ashen Vale: river with two fords, an enemy ash plateau reached by a main ramp
  and a narrow goat path, six gold mines, four goblin warrens, a hand-tuned road
  network, validated A* connectivity.
- Emberhold: workers, footmen, archers, knights, priests, a leveling hero with
  four abilities, eight buildings including Keep, Sanctum, Blacksmith and Altar.
- Hollow Host AI: economy, production, defence, escalating waves, ambush at the
  ford, and the Hollow King as the final wall.
- Economy, supply, upgrades, fog of war, minimap, command card, tooltips,
  control groups, construction, queues, rally points, bounties.
- Hero items: 15-piece shop (six components, seven forged, two masterworks)
  with recipes, forge fees, a six-slot satchel, 50% sell-back and two actives
  (Ashen Step blink, Ember Flask heal). Opens with `P` at the Emberhold.
- Audio: 20 SFX and three seamless music beds (menu / battle / night), mixed at
  a −18 dB bed.
- Victory/defeat with stats, pause/settings/controls/credits, difficulty select.

## QA / headless

Everything runs headless with SDL’s dummy drivers:

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  .venv/bin/python -m emberfall.main --qa --scene base --shot out.png --frames 120

EMBERFALL_QA=state SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  .venv/bin/python -m emberfall.main --qa --scene play --autoplay --speed 4 --frames 4000
```

Scenes: `title intro base battle siege victory defeat play shop`. `EMBERFALL_QA=state`
prints one JSON line per simulated second (fps, resources, unit counts, wave,
selection, music, hero items and hero stats).

Item shop / crafting probe (23 checks, drives the real UI hit-test path):

```bash
.venv/bin/python tools/item_probe.py       # -> design/notes/item-probe.md
```

Campaign probe (every mission boots at its size with its boss; mission 1 must
autoplay to a win and must never feel like a war):

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  .venv/bin/python tools/campaign_probe.py         # -> .council/evidence/campaign-probe-01.json
```

`--autoshop` makes `--autoplay` keep the hero shopping, so long demo/soak runs
exercise the satchel too. Item icons are generated from SVG sources:
`tools/make_item_icons.py`.

## Architecture

```
emberfall/
  main.py              launch shim
  src/
    app.py             window, state machine, input, camera, QA hooks
    world.py           entities, orders, pathfinding movement, economy, combat, hero, fog
    ai.py              Hollow Host economy, waves, defence, boss
    ui.py              HUD, command card, tooltips, minimap, menus (mission select)
    campaign.py        nine-mission scenario table, bosses, progression save
    art.py             procedural art management + Flare integration
    flare_units.py     composited 8-direction animated unit sprites
    flare_buildings.py composed Flare building sprites
    flare_terrain.py   painterly ground, trees, plants
    render.py          baked isometric terrain, props, entity sorting, fog, lights
    mapgen.py          Ashen Vale layout, parameterised for campaign sizes/flips
    pathfind.py        A* + cliff/ramp rules + string pulling
    audio.py           music/SFX bus
```

## Credits & licences

- Design, simulation, UI, direction: **deepseek**.
- Audio, independent QA, art direction: **mimo**.
- Art: [Flare](https://github.com/clintbellanger/flare-game) by Clint Bellanger
  and contributors — **CC-BY-SA 3.0**. See `LICENSES-FLARE.md`.
- UI icons and brand marks: original for this project, CC-BY-SA 4.0.
- Engine: pygame-ce (LGPL-2.1+). The game code is MIT.

This is a beta. Known rough edges: building compositions are a first pass,
fog edges are tile-hard, and the AI economy is tuned for a 15–20 minute mission.
