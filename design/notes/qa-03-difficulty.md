# qa-03 difficulty check — does Squire/Knight/Warlord actually differ?

Method: `design/notes/qa03_difficulty.py` — same scene (`siege`), same
autoplay controller, same speed (6×), only `--difficulty` changes. Window up
to 260 s wall time per run. Headless.

| difficulty | outcome | game-time to outcome | player units left | enemy peak |
|---|---|---|---|---|
| squire | victory | **165.0 s** | 25 | 25 |
| knight | victory | **180.1 s** | 21 | 25 |
| warlord | victory | **211.4 s** | 20 | 25 |

## Reading

- **The gradient is real and monotonic**: warlord takes **+28 % longer** to
  close out the same siege than squire, and arrives with 5 fewer units alive.
  Ordering squire < knight < warlord holds on both axes, so the 0.8 / 1.0 /
  1.3 AI multipliers are doing something visible.
- **The spread is modest.** A 28 % time delta and a 20 % survivor delta is a
  readable difference for a stat sheet, but a confident player may not *feel*
  much between squire and knight. If we want the labels to mean something,
  the cheapest lever is enemy HP/damage rather than income (income only shows
  up later in a long mission).
- `waves_seen` is empty because the siege scene has no wave scheduler — that
  axis needs the `play` scene (separate run).
- Enemy peak is 25 in all three, i.e. the siege scene's population is
  scripted/capped rather than difficulty-scaled — consistent with the new
  50-unit production cap; not a bug, just not a difficulty signal.

Verdict: **PASS as implemented, with a recommendation** to widen the gap if
difficulty labels are meant to be felt in a single sitting.
