# Emberfall — collaboration contract (deepseek ⇄ mimo)

**Read this before touching the repo.** Two agents share this workspace.
We ship ONE game. The user wants a Warcraft-3-like RTS beta, ready to play when
they wake up. Deadline discipline beats elegance.

## Channel

- Broker: `python3 broker.py --port 8770` (already running).
- Durable log: `design/bus/messages.jsonl`.
- Send: `python3 bus.py send --from mimo --to deepseek --text "..."`
- Watch: `python3 bus.py watch --name mimo`
- Long-form notes: drop files in `design/notes/` and mention them on the bus.
- Poll the bus before starting any new work package.

## Ownership (avoid edit collisions)

| path | owner | notes |
|---|---|---|
| `game/` (all code, HTML, CSS) | **deepseek** | single source of truth; mimo does not edit |
| `assets/audio/` | **mimo** | SFX + music, exact filenames from `design/ASSET-CONTRACT.md` |
| `assets/art/` | **mimo** | optional painted textures/icons, transparent PNG |
| `design/notes/` | **mimo** | lore, map critique, balance reports, playtest notes |
| `tools/qa/` | **mimo** | automated browser QA + screenshots |
| `README.md`, `design/DESIGN.md` | **deepseek** | |

Rule: if you want to change something you don't own, put a proposal in
`design/notes/proposals/` and send the bus message. Deepseek has the final call
per the user.

## Product decision (locked unless I say otherwise)

- Title: **EMBERFALL — The Hollow Crown**
- 2.5D isometric RTS, Canvas2D, vanilla ES modules, no build step, served from
  `game/`. Runs in Chromium/Firefox at 60 fps, 1280×720 and up.
- One handcrafted mission map ("Ashen Vale", 84×84 tiles) + skirmish replay of
  it with 3 difficulties. Player = Emberhold humans. Enemy = Hollow Host undead.
- Core: workers/gold/lumber/food, 8 buildings, 6 units, a leveling hero with 4
  abilities, fog of war, minimap, command card, enemy AI with escalating waves,
  victory/defeat.
- Art direction: storybook-isometric, thick ink outlines, warm ember humans vs
  cold violet undead, light top-left. Coherent by construction.

## What I need from mimo (in priority order)

1. **QA loop (highest value):** once `game/index.html` boots, run headless
   Chromium screenshots at 1440×900, play the first 5 minutes via scripted
   clicks, and file concrete bugs with repro steps in `design/notes/qa-NN.md`.
   Check: art coherence, map readability, HUD overlap, console errors, fps.
2. **Audio:** exact contract in `design/ASSET-CONTRACT.md`. Synthesized is fine
   and preferred (no licensing risk). Short, tasteful, mixed quietly.
3. **Map/lore critique:** look at `design/map-preview.png`, tell me what reads
   badly (chokepoints, expansion fairness, visual noise) — one pass, actionable.
4. If you already started your own build, tell me now: we merge the best parts
   or you keep it as a prototype under `prototype-mimo/`, but `game/` ships.

Reply on the bus with: what you've built so far, which of the four you take,
and any blocker. If I don't hear back, I'll assume 1+2 and keep going.


## Operating rule (user directive, 2025-11-09)

**Always run headless.** Every build, test, screenshot and QA run uses
`SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy` and saves frames with
`pygame.image.save` / the game's `--shot` hook. No visible windows, no Xvfb
dependency, no focus grabbing. Xvfb + screenshot tools are a last-resort
fallback only for reproducing a bug that headless cannot show.
