# RELEASE STATUS — Emberfall: The Hollow Crown

Compiled by mimo, 10 Nov 00:50. Objective gates first, then the user-reported
complaints, then what is still open.

## One-command gate

```
python3 tools/qa/release_check.py        # 44 checks: 0 FAIL / 0 WARN
```

It aggregates: audio contract (20 SFX + 3 music, decode + SDL load), icon
contract, Flare building crops + licence, README run instructions, map audit,
headless boot, plus the reports of every probe below.

| probe | result | file |
|---|---|---|
| controls (incl. build end-to-end) | **19/19** | `design/notes/qa-input-01.md` |
| display/input at any window size | **15/15** | `design/notes/qa-display.md` |
| real X server, two screen sizes, real cursor | **10/10** | `design/notes/qa-xwindow.md` |
| crowd motion / collision | **6/6** | `design/notes/qa-collision.md` |
| animation sweep (16 rigs × 4 states × 4 facings) | **0 frozen** | `design/notes/anim-audit-01.md` |
| features vs DESIGN.md | **32/32** | `design/notes/feature-audit-01.md` |
| map structure (connectivity/fairness) | **PASS, 0 findings** | `design/notes/map-audit-01.md` |
| ground lattice metric | **1.26 PASS** (was 1.52) | `design/notes/lattice-pass-aligned.json` |
| qa-03 (hall-loss, siege conversion) | **3/3** | `design/notes/qa-03-checks.json` |
| pacing / difficulty | gradient PASS, Knight open | `design/notes/qa-04-pacing.md` |

## The four complaints, closed

1. **Resolution** — logical 1600×900 canvas letterboxed onto real windows
   (`present()`), `map_pos()` inverse for every mouse path, NOFRAME window for
   the Wayland force-tilt bug, Alt+Enter/F11 both supported.
2. **Controls** — one coordinate transform for events, HUD, edge-scroll, aim
   cursor; proven with real xdotool clicks on a real X server at 1920×1080 and
   1366×768, and after a live resize to 1100×700; construction works end to end.
3. **Animation** — Flare anchor math fixed (deepseek, from my `flare-import.md`),
   ballista given an attack animation it never had, gate shows 0 frozen frames.
4. **Assets** — 14/14 v2 buildings wired (silhouette split passes), rebuilt
   smithy + machicolated tower, baked biome terrain rows, seam-blended sheets,
   water wireframe removed, fog feathered, faction cloth; the ground lattice
   chain measured 1.52 → 1.39 → 1.26.

## Release artifacts

- `dist/Emberfall/Emberfall` — PyInstaller onedir, rebuilt 00:30, verified
  headless (base/siege/title clean, zero tracebacks).
- `./play.sh` — first run creates `.venv` and installs pygame-ce/cairosvg.
- **Fresh-tree test passed**: `git worktree` at HEAD, `play.sh` bootstrapped a
  clean environment and ran 300 frames with a shot (`design/notes/fresh-clone.log`).
- Attribution: `LICENSES-FLARE.md` (CC BY-SA 3.0, Clint Bellanger + Flare
  contributors), in-game credits mention Flare.

## Validation on the full game

14,000-frame autoplay run, zero crashes, economy healthy (Gold 4,340,
Lumber 3,010 — it was 0 before the autoplay gather fix), clean defeat screen.

## Open — needs a human or deepseek

1. **Pacing call**: squire survives 520 s, knight's hall falls at 5:24 *inside
   wave 1*, warlord at 5:01 (`qa-04-pacing.md`). Autoplay never towers or
   micros, so one human game decides whether knight's wave 1 is tuned.
2. **deepseek has been silent since 21:15** (their bus watcher is alive — my
   messages are logged). Pending their call: edge/water sheet adoption
   (`design/notes/flare-tiles.md` §7), and three engine edits I made after
   offering them on the bus (baked biome rows, cliff shading ±5%, pass-1
   diamond alignment) — each revertible in one commit.
3. Sprite nits in flight: town-hall stoop reads as a floating slab, farm is a
   twin of the town hall (fix agent running).
4. Visual-overlap of units at spawn is a **sprite-scale** question, not a
   separation constant — widening separation to 1.5× broke group arrival and
   was reverted with rationale (`c7660a7`).

## Honest AAA answer

No. It is a strong, honest beta: one mission + skirmish, three music loops,
one art pipeline two passes short of a painted set. The complaints that
brought us here are fixed and gated; depth (campaign, more maps, more music)
is what stands between this and the user's bar.
