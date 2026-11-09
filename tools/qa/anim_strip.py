#!/usr/bin/env python3
"""Animation evidence strip (mimo, tools/qa/).

Renders the engine's own unit sprite pipeline into labelled contact sheets so
animation claims can be *seen* instead of asserted: does walk actually advance
frames, does attack differ from idle, do the 8 facings differ (or pop), do
layers stay aligned.

    .venv/bin/python tools/qa/anim_strip.py --rig footman
    .venv/bin/python tools/qa/anim_strip.py --rig ghoul --frames 8
"""
from __future__ import annotations

import argparse
import hashlib
import math
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402



def summary(art, args) -> int:
    """Numeric animation audit across every rig, state and facing."""
    from emberfall.src.defs import ENEMY, PLAYER, UNITS

    anims = [a.strip() for a in (args.anims or "idle,walk,attack,death").split(",")]
    dirs = [0, 2, 4, 6]
    rows = []
    issues = []
    for rig in sorted(UNITS):
        team = ENEMY if UNITS[rig].get("enemy") else PLAYER
        for anim in anims:
            for d in dirs:
                keys, bases = [], []
                for f in range(args.frames):
                    try:
                        img, ax, ay = art.unit(UNITS[rig]["rig"], d, anim, f, team)
                    except Exception as exc:  # noqa: BLE001
                        issues.append(f"{rig}/{anim}/d{d}: render error {exc}")
                        keys, bases = [], []
                        break
                    keys.append(hashlib.md5(pygame.image.tobytes(img, "RGBA")).hexdigest()[:8])
                    # baseline = lowest non-transparent row (feet line)
                    rect = img.get_bounding_rect()
                    bases.append(rect.bottom)
                uniq = len(set(keys))
                if not keys:
                    continue
                base_spread = max(bases) - min(bases)
                rows.append({"rig": rig, "anim": anim, "dir": d,
                             "unique": uniq, "frames": len(keys),
                             "feet_spread_px": base_spread})
                if anim in ("walk", "attack", "death") and uniq <= 1:
                    issues.append(f"{rig}/{anim}/d{d}: FROZEN ({uniq} unique frame)")
                # idle deliberately breathes (Flare idles are 4-frame loops and
                # procedural rigs step per frame) — not an anomaly, so it is
                # recorded in the table but never flagged.
                if base_spread > 14 and anim in ("idle", "attack"):
                    issues.append(f"{rig}/{anim}/d{d}: feet line swings {base_spread}px "
                                  "(anchor jitter -> sliding)")
    lines = ["# anim-audit-01 — every rig x state x facing (numeric)", "",
             "| rig | anim | dir | unique/frames | feet spread px |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['rig']} | {r['anim']} | d{r['dir']} | "
                     f"{r['unique']}/{r['frames']} | {r['feet_spread_px']} |")
    # faction colour separation: if player and enemy means converge, the teams
    # stop reading at a glance (this regressed once already)
    try:
        def accent_share(rig, team, kind):
            """Fraction of opaque pixels wearing the faction accent.

            Mean colour barely moves when a tabard is 5% of the sprite, so the
            gate measures accent *coverage* instead: warm red/orange for the
            player, violet/cold for the enemy. This regressed to ~0 once
            already (teams looked identical in-game).
            """
            img, _, _ = art.unit(UNITS[rig]["rig"], 0, "idle", 0, team)
            w, h = img.get_size()
            hit = n = 0
            for y in range(0, h, 2):
                for x in range(0, w, 2):
                    r, g, b, a = img.get_at((x, y))
                    if a <= 200:
                        continue
                    n += 1
                    if kind == "warm" and r - max(g, b) > 35:
                        hit += 1
                    elif kind == "cold" and b - r > 10 and b >= g:
                        hit += 1
            return (hit / n) if n else 0.0

        pw = accent_share("footman", PLAYER, "warm")
        ec = accent_share("ghoul", ENEMY, "cold")
        rows.append({"rig": "TEAMS", "anim": f"accent warm={pw:.3f} cold={ec:.3f}",
                     "dir": "-", "unique": 0, "frames": 0, "feet_spread_px": 0})
        if pw < 0.03:
            issues.append(f"player accent coverage {pw:.3f} < 0.03 (footman wears no crimson/orange)")
        if ec < 0.03:
            issues.append(f"enemy accent coverage {ec:.3f} < 0.03 (ghoul wears no violet/cold)")
    except Exception as exc:  # noqa: BLE001
        issues.append(f"team colour check failed: {exc}")

    lines += ["", "## Anomalies", ""]
    lines += [f"- {i}" for i in issues] or ["- none"]
    lines.append("")
    out = os.path.join(ROOT, "design", "notes", "anim-audit-01.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(json.dumps({"anim": {"rows": len(rows), "issues": len(issues)}}))
    for i in issues[:40]:
        print("  !", i)
    print(f"wrote {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rig", default="footman")
    ap.add_argument("--anims", default="idle,walk,attack,death")
    ap.add_argument("--dirs", default="0,2,4,6")
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--out", default=None)
    ap.add_argument("--summary", action="store_true",
                    help="numeric audit of every rig x anim x direction; writes "
                         "design/notes/anim-audit-01.md and prints anomalies")
    ap.add_argument("--per-dir", action="store_true",
                    help="one row per (anim, direction) so continuity in a single "
                         "facing is visible instead of mixing facings per column")
    args = ap.parse_args()

    from emberfall.src.art import Art
    from emberfall.src.defs import PLAYER, ENEMY, UNITS

    pygame.init()
    pygame.display.set_mode((1600, 900))  # convert_alpha needs a display
    art = Art()

    if args.summary:
        return summary(art, args)
    rigs = sorted(UNITS)
    if args.rig not in rigs and args.rig != "all":
        print(f"unknown rig {args.rig!r}; have: {rigs}")
        return 2

    target = [args.rig] if args.rig != "all" else ["footman", "ghoul", "hollow-king"]
    anims = [a.strip() for a in args.anims.split(",") if a.strip()]
    dirs = [int(d) for d in args.dirs.split(",") if d.strip()]

    CELL_W, CELL_H, PAD, LABEL = 190, 200, 10, 22
    rows = [(rig, anim) for rig in target for anim in anims]
    fixed_dir = None
    if args.per_dir:
        rows = [(rig, f"{anim}|d{d}") for rig in target for anim in anims for d in dirs]
    cols = args.frames
    sheet = pygame.Surface((cols * CELL_W + 120, len(rows) * CELL_H + 60), pygame.SRCALPHA)
    sheet.fill((26, 24, 28))
    font = pygame.font.SysFont(None, 16)

    report: dict[str, dict] = {}
    for ri, (rig, label) in enumerate(rows):
        team = ENEMY if UNITS[rig].get("enemy") else PLAYER
        anim = label.split("|")[0]
        fixed_dir = int(label.split("|d")[1]) if "|d" in label else None
        hashes = []
        for f in range(cols):
            d = fixed_dir if fixed_dir is not None else dirs[f % len(dirs)]
            try:
                img, ax, ay = art.unit(UNITS[rig]["rig"], d, anim, f, team)
            except Exception as exc:  # noqa: BLE001
                print(f"  render failed {rig}/{anim}/dir{d}/f{f}: {exc}")
                continue
            key = hashlib.md5(pygame.image.tobytes(img, "RGBA")).hexdigest()[:8]
            hashes.append((d, f, key))
            dst = pygame.Rect(120 + f * CELL_W, 40 + ri * CELL_H, CELL_W, CELL_H)
            sheet.blit(img, (dst.x + CELL_W // 2 - ax, dst.y + CELL_H - 24 - ay))
        uniq = len({k for _, _, k in hashes})
        report[f"{rig}/{label}"] = {
            "frames_rendered": len(hashes),
            "unique_frames": uniq,
            "sequence": [k for _, _, k in hashes],
            "dirs_sampled": [d for d, _, _ in hashes],
        }
        lbl = font.render(f"{rig}/{label} uniq={uniq}/{len(hashes)}", True, (235, 220, 185))
        sheet.blit(lbl, (6, 44 + ri * CELL_H))
    hdr = font.render(f"engine unit pipeline — cols = animation frames, dirs cycle {dirs}",
                      True, (200, 210, 230))
    sheet.blit(hdr, (6, 10))

    out = args.out or os.path.join(ROOT, "design", "notes",
                                    f"anim-{args.rig}{'-perdir' if args.per_dir else ''}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pygame.image.save(sheet, out)

    # verdicts
    issues = []
    for k, v in report.items():
        if v["unique_frames"] <= 1 and "idle" not in k:
            issues.append(f"{k}: every frame identical (no animation)")
        if v["frames_rendered"] and v["unique_frames"] == v["frames_rendered"] and "idle" in k:
            issues.append(f"{k}: idle is unique per frame (idle should hold one pose)")
    print(json.dumps({"anim_report": report, "issues": issues}, indent=1))
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
