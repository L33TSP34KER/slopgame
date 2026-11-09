#!/usr/bin/env python3
"""Feature audit: what design/DESIGN.md promises vs what the build contains.

Static checks (grep the engine), dynamic checks (import defs, count the
rosters) and asset wiring (every contracted sound actually referenced by the
game). Writes design/notes/feature-audit-01.md with PASS / PARTIAL / GAP.

    .venv/bin/python tools/qa/feature_audit.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(ROOT, "emberfall", "src")
SFX_DIR = os.path.join(ROOT, "assets", "audio", "sfx")
MUSIC_DIR = os.path.join(ROOT, "assets", "audio", "music")

ROWS: list[tuple[str, str, str]] = []


def row(item: str, status: str, evidence: str) -> None:
    ROWS.append((item, status, evidence))


def read_src() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in sorted(os.listdir(SRC)):
        if name.endswith(".py"):
            out[name] = open(os.path.join(SRC, name), encoding="utf-8",
                             errors="replace").read()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "design", "notes",
                                                  "feature-audit-01.md"))
    args = ap.parse_args()

    src = read_src()
    blob = "\n".join(src.values())

    # ---------------------------------------------------------------- rosters
    sys.path.insert(0, ROOT)
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    try:
        from emberfall.src.defs import ABILITIES, BUILDINGS, DIFFICULTY, UPGRADES, UNITS
    except Exception as exc:  # noqa: BLE001
        row("engine imports", "GAP", f"could not import defs: {exc}")
        ABILITIES, BUILDINGS, DIFFICULTY, UPGRADES, UNITS = {}, {}, {}, {}, {}

    want_human = {"townhall", "keep", "farm", "barracks", "mill", "blacksmith",
                  "sanctum", "tower", "altar"}
    want_undead = {"necropolis", "ziggurat", "crypt", "slaughterhouse", "temple",
                   "bonetower"}
    want_units = {"worker", "footman", "archer", "knight", "priest", "ballista",
                  "hero", "ghoul", "fiend", "necromancer", "abomination",
                  "revenant", "skeleton", "hollow-king"}
    row("buildings: 9 Emberhold", "PASS" if want_human <= set(BUILDINGS) else "GAP",
        f"missing {sorted(want_human - set(BUILDINGS)) or 'none'}")
    row("buildings: 6 Hollow Host", "PASS" if want_undead <= set(BUILDINGS) else "GAP",
        f"missing {sorted(want_undead - set(BUILDINGS)) or 'none'}"
        f" (roster total {len(BUILDINGS)})")
    row("units: 6 player + hero + 6 enemy + boss",
        "PASS" if want_units <= set(UNITS) else "GAP",
        f"missing {sorted(want_units - set(UNITS)) or 'none'} "
        f"(roster total {len(UNITS)}: extras "
        f"{sorted(set(UNITS) - want_units) or 'none'})")
    row("hero abilities Q/W/E/R",
        "PASS" if {"ember-lance", "aegis", "consecrate", "daybreak"} <= set(ABILITIES)
        else "GAP", f"ABILITIES keys: {sorted(ABILITIES)}")
    row("blacksmith / keep upgrades",
        "PASS" if UPGRADES else "GAP", f"UPGRADES keys: {sorted(UPGRADES)}")
    row("difficulties squire/knight/warlord",
        "PASS" if {"squire", "knight", "warlord"} <= set(DIFFICULTY) else "GAP",
        f"{sorted(DIFFICULTY)}")

    # ------------------------------------------------------------ static checks
    checks = [
        ("fog of war (explored + visible states)",
         [r"explored", r"fog"], "render.py"),
        ("day/night cycle", [r"day_night|daytime|night_t|time_of_day|dusk"], "world/render"),
        ("minimap with fog + camera rect", [r"minimap_rect|_draw_minimap"], "ui.py"),
        ("box select + shift add", [r"def box_select", r"KMOD_SHIFT"], "app.py"),
        ("control groups ctrl+1..9", [r"control_groups", r"KMOD_CTRL"], "app.py"),
        ("attack-move / stop / hold hotkeys",
         [r"attackmove|attack_move_mode", r"K_s\b", r"K_h\b|hold"], "app.py/ui.py"),
        ("build placement ghost + validity",
         [r"self\.placement", r"placement_valid"], "app.py/world"),
        ("camera: arrows + edge + middle-drag",
         [r"K_UP\b", r"MOUSEMOTION|edge", r"button == 2"], "app.py"),
        ("fullscreen: F11 and Alt+Enter",
         [r"K_F11", r"KMOD_ALT"], "app.py"),
        ("idle worker F1 / objectives O / pause Esc",
         [r"K_F1", r"K_o\b", r"K_ESCAPE"], "app.py"),
        ("subgroup tabs (Tab)", [r"K_TAB|cycle_subgroup"], "app.py/ui.py"),
        ("victory + defeat screens with stats",
         [r"victory", r"defeat", r"Gold gathered|gold_gathered|Kills"], "app"),
        ("objective panel + bonus objective",
         [r"OBJECTIVE_MAIN", r"OBJECTIVE_BONUS|warrens"], "defs/ui"),
        ("alerts (under attack / low resources)",
         [r"alert|under attack|not enough"], "ui/world"),
        ("settings: music/sfx volume",
         [r"music_vol", r"sfx_vol"], "ui/audio"),
        ("title menu: campaign/skirmish/controls/credits/quit",
         [r"campaign", r"skirmish", r"controls", r"credits", r"quit"], "ui.py"),
        ("enemy AI wave scheduler",
         [r"wave", r"EnemyAI"], "ai/world"),
        ("creep camps + bounty",
         [r"camp|bounty"], "world/mapgen"),
        ("hero XP + levels + altar revive",
         [r"HERO_LEVELS", r"xp", r"hero_revive|revive"], "defs/world"),
        ("gather loop (gold + lumber round trip)",
         [r"cmd_gather|gather", r"carry"], "world/app"),
        ("in-game credits mention Flare attribution",
         [r"Flare", r"Bellanger"], "ui/credits"),
    ]
    for item, patterns, where in checks:
        hits = [p for p in patterns if re.search(p, blob)]
        status = "PASS" if len(hits) == len(patterns) else (
            "PARTIAL" if hits else "GAP")
        missing = [p for p in patterns if p not in hits]
        row(item, status,
            f"evidence in {where}" + (f"; not found: {missing}" if missing else ""))

    # ----------------------------------------------------------- audio wiring
    sfx = sorted(f[:-4] for f in os.listdir(SFX_DIR) if f.endswith(".ogg")) \
        if os.path.isdir(SFX_DIR) else []
    music = sorted(f[:-4] for f in os.listdir(MUSIC_DIR) if f.endswith(".ogg")) \
        if os.path.isdir(MUSIC_DIR) else []
    row("audio: 20 contracted SFX present", "PASS" if len(sfx) >= 20 else "GAP",
        f"{len(sfx)} files")
    row("audio: 3 music loops present", "PASS" if len(music) >= 3 else "GAP",
        f"{music}")
    unwired = [s for s in sfx if f'"{s}"' not in blob and f"'{s}'" not in blob]
    row("audio: SFX referenced by the game code",
        "PASS" if not unwired else ("PARTIAL" if len(unwired) <= 6 else "GAP"),
        f"{len(sfx)-len(unwired)}/{len(sfx)} referenced"
        + (f"; not referenced: {unwired}" if unwired else ""))
    music_refs = [m for m in music if f'"{m}"' in blob or f"'{m}'" in blob]
    row("audio: music tracks referenced", "PASS" if music_refs else "GAP",
        f"{music_refs}")

    # --------------------------------------------------------------- lore copy
    lore_path = os.path.join(ROOT, "design", "notes", "lore-copy-01.md")
    if os.path.exists(lore_path):
        sigs = ["The Hollow Crown is broken", "Destroy the Necropolis",
                "Ember Lance"]
        used = [s for s in sigs if s in blob]
        row("copy: my lore pack wired into the game",
            "PASS" if len(used) == len(sigs) else
            ("PARTIAL" if used else "GAP"),
            f"found {len(used)}/{len(sigs)} signature lines in engine"
            + ("" if used else " (game uses its own copy)"))

    # ----------------------------------------------------------------- report
    fails = [r for r in ROWS if r[1] == "GAP"]
    parts = [r for r in ROWS if r[1] == "PARTIAL"]
    lines = ["# feature-audit-01 — DESIGN.md promises vs build", "",
             f"**{len(fails)} GAP / {len(parts)} PARTIAL / {len(ROWS)} checks** "
             "— static + dynamic audit by mimo.", "",
             "| feature | status | evidence |", "|---|---|---|"]
    for item, status, evidence in ROWS:
        lines.append(f"| {item} | {status} | {evidence.replace('|', '/')} |")
    lines += ["", "## Gaps to close before release", ""]
    if fails:
        for item, _, evidence in fails:
            lines.append(f"- **{item}** — {evidence}")
    else:
        lines.append("- none")
    lines.append("")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(json.dumps({"qa": {"feature_gaps": len(fails),
                             "feature_partial": len(parts),
                             "feature_checks": len(ROWS)}}))
    for item, status, evidence in ROWS:
        if status != "PASS":
            print(f" {status:7} {item}: {evidence[:150]}")
    print(f"wrote {args.out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
