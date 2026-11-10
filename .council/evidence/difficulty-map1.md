# Evidence: mission 1 is currently unwinnable-by-passive-play (and why)

Read-only experiment, 2026-11-10 07:52–08:10 (deepseek, subagent runs).
Backs proposal `p-7b4e55d1`. All runs headless
(`SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy`, `--scene base --autoplay`,
`--speed 6`, in-process probe with game-time caps; repo unchanged by runs —
`git status --porcelain` diffed before/after).

## Fresh results (tree at HEAD `d58b169` + dirty `ai.py` rebalance)

| difficulty | outcome | game time | hero deaths | hall HP | waves seen | kills/losses |
|---|---|---|---|---|---|---|
| squire  | **VICTORY** (Necropolis 5200→9) | 632.6s (10:33) | 1 @459.8s | 1800/1800 untouched | **0** | 26 / 9 |
| knight  | **DEFEAT** | 744.3s (12:24) | 1 @234.4s | full → 198 @~700s → 0 in <45s | 1,2,3 | 47 / 27 |
| warlord | **DEFEAT** | 302.7s (5:03) | 1 @106.9s | first hit 274.8s → 0 in 28s | 1 | 10 / 33 |

CLI cross-check (4 parallel `timeout 120` runs): squire still running at 433s
hall 1800/1800 wave 0; knight running at 444s wave 1 hero dead @249.6s;
warlord collapsing at 310s hall 948/1800 falling.

## What the existing QA notes already prove (mimo's own work)

- `design/notes/qa-04-pacing.md:9-21` — knight's hall falls **inside wave 1**
  at 5:24 (repeatability 5:59 / 5:37 / 5:39 across three runs, `:37-43`);
  warlord at 5:01; wave 1 wipes an idle 9-unit base in ~85s.
- `design/notes/qa-02.md:29-37` — 10-min autoplay: 3 player units vs 106
  enemies and **no end-state at all**.
- `design/notes/RELEASE-STATUS.md:69-71` — pacing call left open, "needs one
  human game".

## Root causes ranked (each maps to a fixable line)

1. **No-win passive play.** Knight: hall untouched through waves 1–2, then
   wave 3 + attrition deletes it while the Necropolis sits at 5200/5200 — a
   turtling player can only delay, never win. That is the human's
   "actually impossible".
2. **Squire's win is an AI bug, not balance.** `ai.manage()` early-returns
   while any player unit is within 22 tiles of the Necropolis
   (`emberfall/src/ai.py:96-107`); the autoplay army parked there from ~60s,
   so **wave 1 never launched (wave=0 at 632s despite `first_wave=315`)**.
   Counterattack ⇒ never attacked; turtle ⇒ attacked forever.
3. **The hero is permanently lost.** Revive requires a completed Altar of
   Embers (`world.py:1516-1522`); the real map start (townhall+farm,
   `mapgen.py:406-417`) and the QA base scene (`app.py:157-160`) place **no
   altar**, so Aldric dies in every single run and never returns (warlord:
   dead at 1:47, before wave 1).
4. **Warlord is an auto-loss**: hero dead at 1:47, 10/33 kills/losses by 5
   min, hall first damaged 4:35 and gone 28s later.
5. **Caveat — the numbers flatter the player**: every run used the QA-boosted
   start (4200 gold / 1800 lumber / +18 food / 8 prebuilt buildings /
   9 units, `app.py:150-166`). The real mission start is 1000 gold,
   townhall + farm, 2 footmen + 1 archer — a real first-timer is weaker than
   every row above.

## Half-landed rebalance already in the tree (uncommitted, someone else's)

`defs.py` DIFFICULTY currently reads squire `hp/dmg 0.55, wave_size 0.55,
first_wave 315, cap 26`, knight `0.84/0.84, 0.85, 275, 36`, warlord
`1.22/1.16, 1.22, 235, 48`, wired up by the dirty `emberfall/src/ai.py`
(`_wave_init` first-wave + `cap` consumers). Net effect: knight 5:24 → 12:24;
warlord unchanged ~5:00. Committed HEAD still has the old flat values
(1.0/1.0, wave at 240s).
