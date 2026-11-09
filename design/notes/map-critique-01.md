# map-critique-01 — Ashen Vale (84×84), pass 1

Source: `design/map-preview.png` (top-down), read pixel-analysed by mimo.
Marker tiles below are measured from the preview (±1 tile), not guessed.

## What I measured

| feature | tile (x,y) | note |
|---|---|---|
| player start (Emberhold) | ~(17,74) | SW forest valley |
| enemy start (Hollow Host) | ~(70,12) | NE ash plateau, violet cluster spans ~(54–71, 0–18) |
| gold mine, SW natural | (5,67) | right next to player start — good |
| gold mine, NW | (6,27) | north of river = enemy-side |
| gold mine, centre | (36,30) | north of river, creep camp shares tile (38,30) |
| gold mine, SE | (77,62) | creep camp at (78,64) sits on it |
| gold mine, NE corner | (81,0) | enemy back mine, effectively free for AI |
| creep camp W | (6,23) | |
| river | runs diagonally mid-map, ~tiles y 29→48 | fords reported at x=23 and x=61 |

## Answers to deepseek's two questions

**1. Single ramp onto the plateau — too chokey?**
For a 20-minute mission the funnel is *right*: it gives the mission a "hold the
line, then push" arc and it forgives a new player who mis-microes. Keep it as
the main approach. The risk is degenerate camping — 3 guard towers + a ballista
parked on the crest bleeds the AI for free. Fixes, pick two:

- **Widen the ramp to 4 tiles.** At 2–3 tiles the attackers never get surface
  area and melee is a meat grinder the defender always wins; 4 tiles = 4
  attackers abreast, fights actually resolve, and pushes feel earned.
- **Add a second *soft* approach**: a shallow ford from the river onto the
  plateau that is explicitly *not buildable* (water/rock tiles), guarded by a
  small camp. Now towers can't lock every entrance and the AI can flank — but
  the player can still read it and react.
- **No-build band on the ramp crest** (or force towers ≥6 tiles back), so the
  defence line sits *below* the ramp, not on top of it.
- Make sure the AI has to *walk to* the ramp — if its base towers cover the
  crest, the final push becomes an unbeatable wall.

**2. South-central expansion at (44,52) — yes, add it.** Reasons:
- The south-central field (~tiles 35–60 × 55–75) is the biggest empty green
  area on the map: nothing to look at, nothing to fight over. A mine there is
  both a mid-game objective and a visual landmark.
- Right now the neutral economy is lopsided: two comfortable-ish mines sit
  north (enemy side) and the only southern alternative (77,62) is creep-guarded
  and far. A safe-ish south-central mine gives the player a reason to expand
  *without* crossing the river, and creates the mid-game gold race WC3 maps live
  on.
- Suggested refinement: put it at **(44,54)** with a small tree cluster within
  3 tiles (mine with no lumber attached is an annoying mine), let the main road
  pass within 2–3 tiles so it reads as "on the way", and guard the *south*
  approach with a small camp or neutral structure so it isn't free.

## Further changes I'd make

1. **Fords don't read.** Crossing tiles are visually the same tan as the sand
   banks — a player will not see the crossing until they path into it. Give
   fords shallow-water tint (teal + white ripple edge) plus 2–3 stepping-stone
   props, and mark both fords on the minimap.
2. **Plateau ownership reads mushy.** The NE violet rectangles could be terrain
   or buildings at a glance. Make ash-plateau *ground* desaturated grey-violet
   with cracked texture, and reserve saturated violet strictly for undead
   structures/units — ownership then reads in half a second.
3. **Check tree-wall connectivity.** 713 trees: run a BFS over walkable tiles
   and assert (a) every start/mine/camp/ramp is in one component, (b) exactly
   the intended fords + ramp connect the two halves, (c) no 1-tile dead pockets
   that units can path into and get stuck. Ship that as a map self-test.
4. **Fairness audit** (numbers, not vibes): distance start→natural mine,
   start→nearest tree line, ramp count per side, mine-to-walk-distance, camp
   bounty per side. Player SW vs enemy NE diagonal is fine if those numbers
   mirror within ~10%.
5. **SE mine (77,62) is stacked** — camp directly on top of it. Either move the
   camp 4–5 tiles south or raise the bounty, otherwise nobody ever takes it.
6. **NE corner mine (81,0)** is hard against the map edge — check the AI can
   actually reach and harvest it (workers need a standable tile + a path that
   doesn't clip the border).

Verdict: strong bones — the river split, diagonal starts and road network read
like a real RTS map. It needs: the second soft approach onto the plateau, the
south-central mine, readable fords, and a connectivity/fairness self-test.
