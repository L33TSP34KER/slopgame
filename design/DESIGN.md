# EMBERFALL — design lock (v1)

**Pitch.** The Hollow Crown has fallen to the Ashen King. You are Marshal Aldric,
last ember of the Emberhold. Raise a keep, wake the vale, and break the
Necropolis before the Host drowns the valley in bone.

**Fantasy.** Warcraft-III-like isometric RTS: hero + army, base building,
gathering, creeping, one handcrafted battlefield, escalating undead pressure.

## Non-negotiables for the beta

- Boots straight from `game/index.html` served over HTTP. No build step, no npm.
- 1280×720 → 2560×1440, 60 fps target with 120+ units.
- Mouse-first RTS controls **and** hotkeys: box select, shift-add, double-click
  type, ctrl-groups, right-click orders, build placement, attack-move (A),
  stop (S), hold (H), hero abilities (Q/W/E/R), minimap click/drag, camera
  edge/WASD/middle-drag, zoom (wheel), idle worker (F1).
- Full HUD: resources, selection portrait + subgroup tabs, command card with
  tooltips/costs/hotkeys, minimap with fog + camera + pings, objectives,
  alerts, hero XP/abilities, pause/settings, victory/defeat with stats.
- Fog of war (explored vs visible), day/night, weather-grade atmosphere.
- One map, fully dressed: cliffs, river + two fords, forests, gold mines,
  ruins, camps, expansions. Asymmetry is fine; fairness is not.

## Factions

**Emberhold (player).** Gold/lumber/food; Town Hall → Keep; Farm, Barracks,
Lumber Mill, Blacksmith, Arcane Sanctum, Guard Tower, Altar of Embers.
Worker, Footman, Archer, Knight, Priest, Ballista. Hero: Marshal Aldric.

**Hollow Host (AI).** Necropolis (destroy = win), Ziggurat, Crypt,
Slaughterhouse, Temple of the Damned, Bone Tower. Ghoul, Crypt Fiend,
Necromancer (summons Skeletons), Abomination, Frost Revenant. Boss: the
Hollow King at the Necropolis.

## Economy / tech

- Start: 800 gold, 220 lumber, 12/20 food. Gold mine 12 000; tree 100 wood.
- Worker trip yields 10 gold / 10 lumber. Farms +6 food, Hall +10.
- Blacksmith: Iron Weapons (+3 dmg), Steel Plate (+3 armor), 2 levels.
- Keep upgrade unlocks Knight + Ballista; Sanctum unlocks Priest.
- Units: Worker 75g · Footman 135g/2f · Archer 130g/20l · Knight 245g/60l/3f
  · Priest 145g/40l · Ballista 180g/80l.
- Buildings: Farm 80g · Barracks 140g/60l · Mill 120g · Blacksmith 140g/50l
  · Sanctum 150g/100l · Tower 110g/70l · Altar 180g/40l · Keep 300g/200l.

## Hero

Marshal Aldric. Levels 1–10 from nearby kills; auto-unlocks:
Q **Ember Lance** (nuke + brief stun) · W **Aegis** (shield) ·
E **Consecrate** (AoE damage + ally heal) · R **Daybreak** (ult: big AoE stun).
Death → revive at Altar after 45 s (or instantly for gold). XP bar in HUD.

## Items / purveyor

The hero carries a six-slot satchel, bought at the Emberhold purveyor (`P`, the
Shop button, or the hero's Purveyor command). Trading needs Aldric within reach
of a Hall, Keep or Altar of Embers, so the shopping trip is a decision, not a
menu — but nothing is lost crafting on the counter.

- **Six components** — Ashwood Blade 240g, Iron Buckler 220g, Ember Tonic 260g,
  Kindled Focus 240g, Trail Greaves 210g, Whetstone 280g — each a small stack
  of one stat.
- **Seven forged items** combine two components plus a forge fee and are
  strictly better than their parts: Ember Warbrand (damage/attack speed),
  Ashen Bulwark (armor/health), Cinder Plate (damage/armor), Pyre Heart
  (health/mana/regen), Windstep Boots (speed/attack speed), Ashen Step
  (blink active, 16 s), Ember Flask (heal-over-time active, 45 s).
- **Two masterworks** combine two forged items: Marshal's Regalia (all-round)
  and Warsong Talisman (aggression).
- One copy of each item; components are consumed by the forge. A purchase is
  refused when parts are missing, gold is short, or the satchel is full.
  Right-click a slot to sell for 50% of the item's whole tree. Actives cost no
  mana, only a cooldown, and clicking one starts its targeting (blink) or
  fires it (heal).
- Item stats are applied as deltas on the entity, so level growth and the
  blacksmith's global upgrades are never overwritten; the satchel is carried
  through death and restored with the revived hero.

## Mission

Intro card + camera pan (skippable). Objective: **destroy the Necropolis.**
Waves: first at 4:00, then every ~2:30, scaling; boss joins the final assault
or defends. Side objective: clear the two creep camps for bounty.
Victory/defeat screens with time, kills, gold gathered, hero level; retry.

Difficulties: Squire (0.8× AI income/HP), Knight (1.0×), Warlord (1.3×, faster
waves). Skirmish reuses the mission with a random wave seed.

## Art direction

- Storybook isometric, 2:1 diamonds, top-left sun, thick ink outlines,
  flat fills + soft internal shading, restrained texture noise.
- Humans: steel, crimson, gold, warm ember light. Undead: bone, violet, sickly
  green, cold rim light. Terrain: moss green, umber dirt, slate cliffs, teal
  water. UI: dark walnut + parchment + brass, serif display type.
- Everything must read at a glance: silhouette first, color second, detail last.
- Motion: walk bob, weapon arcs, hit flashes, dust, embers, floating motes,
  water shimmer, swaying trees, torch light at night.

## Audio direction

Low mixed ambient bed, sparse percussion, distant horns. SFX short, dry,
satisfying; never louder than the music bed. See `ASSET-CONTRACT.md`.

## Tech

Vanilla ES modules + Canvas2D + DOM HUD + WebAudio. Data-driven defs.
Chunked baked terrain, sprite-sheeted unit rigs, A* + steering, spatial hash,
512-unit cap, fog grid, minimap bake, fixed 30 Hz sim with render interpolation.
