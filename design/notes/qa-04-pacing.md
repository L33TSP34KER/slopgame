# qa-04 — pacing / difficulty evidence (real mission scene, autoplay)

Method: `design/notes/qa_play_difficulty.py` — `--scene play --autoplay
--speed 4`, identical controller in all three runs, only `--difficulty`
changes. Window: up to 520 in-game seconds (capped), headless.

| difficulty | outcome | end time | waves faced | army at end | hall HP | lumber gathered |
|---|---|---|---|---|---|---|
| squire | **survived** (`play`) | 520 s (cap) | 1, 2 | 24 | 1800/1800 | 4,360 |
| knight | **defeat** | **324 s (5:24)** | 1 only | 9 | 0 | 2,900 |
| warlord | **defeat** | **302 s (5:01)** | 1 only | 11 | 0 | 2,290 |

## Reading

- The gradient is real and correctly ordered: squire outlives the window,
  knight dies 22 s earlier than warlord, warlord fastest. The 0.8/1.0/1.3
  multipliers are visible in the real mission, not just the siege scene.
- **The load-bearing fact: knight's hall falls during WAVE 1** (wave 2 never
  spawns). Wave 1 arrives at 4:00 per design; the undefended autoplay base —
  hall + farm + barracks + 9 units — is gone by 5:24. So wave 1 alone removes
  an idle base in ~85 seconds.
- Whether that is "unforgiving as advertised" or "too hot for a first-time
  player on the default difficulty" is a **human playtest call**, not
  something I can settle headlessly: autoplay never builds a guard tower and
  never micros, which a person would.
- Concrete options if a human confirms it is too hot (deepseek's numbers):
  trim wave 1 composition/size at knight, delay wave 1 past 4:00, or lower the
  hall's apparent priority so the AI splits damage across buildings.
- Also worth noting: lumber income now runs in all three runs (2,290–4,360),
  so the economy side of the demo is healthy — this is a defence problem, not
  an income problem.

Verdict: **gradient PASS, pacing OPEN pending a human playtest.**

## Repeatability (added 01:02)

Three independent autoplay runs on Knight, different commits, different speeds:
**5:59, 5:37, 5:39** — the hall consistently falls during wave 1 within ±12
seconds of each other. This is not run-to-run noise; the pattern is stable, so
the pacing question can be answered by one human game rather than a sample.
Latest run also confirms the defeat overlay holds cleanly while frames keep
running (no softlock after the loss) and the economy numbers repeat
(Lumber 3,010, Gold ~4,400).
