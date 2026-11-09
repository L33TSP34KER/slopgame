#!/usr/bin/env python3
"""Independent map audit for Ashen Vale (mimo, tools/qa/).

Generates the map through the game's own generator (read-only import) and
checks the things a player feels but a screenshot can't show:

- connectivity: every start, mine and camp reachable from both bases
- route count: how many genuine ways cross the river (fords, ramps, goat path)
- dead pockets: walkable components nothing can enter from a base
- symmetry/fairness: path distances and local resources per side
- build space: clear tiles around each hall (can you actually build a base?)

    python3 tools/qa/map_audit.py            # markdown report + {"qa": ...} line
    python3 tools/qa/map_audit.py --json     # machine-readable only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from src.mapgen import generate_map  # noqa: E402  (path setup above)
from src.pathfind import walkable, find_path, nearest_walkable  # noqa: E402
from src.defs import PLAYER, ENEMY, BUILDINGS  # noqa: E402

DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]


def bfs(m, start):
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if (nx, ny) in seen or not walkable(m, nx, ny):
                continue
            if dx and dy and not (walkable(m, x + dx, y) or walkable(m, x, y + dy)):
                continue  # no diagonal corner cutting
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def components(m):
    seen = set()
    comps = []
    for y in range(m.h):
        for x in range(m.w):
            if walkable(m, x, y) and (x, y) not in seen:
                c = bfs(m, (x, y))
                seen |= c
                comps.append(c)
    comps.sort(key=len, reverse=True)
    return comps


def path_len(m, a, b):
    if a is None or b is None:
        return None
    p = find_path(m, a, b)
    if not p:
        return None
    total = 0.0
    for i in range(1, len(p)):
        total += ((p[i][0] - p[i - 1][0]) ** 2 + (p[i][1] - p[i - 1][1]) ** 2) ** 0.5
    return round(total, 1)


def near(m, x, y, radius, pred):
    n = 0
    for ty in range(int(y - radius), int(y + radius) + 1):
        for tx in range(int(x - radius), int(x + radius) + 1):
            if m.inb(tx, ty) and (tx - x) ** 2 + (ty - y) ** 2 <= radius * radius and pred(tx, ty):
                n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "design", "notes", "map-audit-01.md"))
    args = ap.parse_args()

    m = generate_map()
    findings: list[str] = []
    checks: dict[str, object] = {}

    comps = components(m)
    main_comp = comps[0]
    checks["walkable_components"] = len(comps)
    checks["main_component_tiles"] = len(main_comp)
    stranded = [c for c in comps[1:] if len(c) >= 3]
    checks["pockets_ge_3_tiles"] = len(stranded)
    if stranded:
        sizes = [len(c) for c in stranded[:8]]
        sample = [sorted(c)[0] for c in stranded[:8]]
        findings.append(f"POCKET: {len(stranded)} walkable region(s) of >=3 tiles are "
                        f"unreachable from the main map — sizes {sizes}, e.g. at {sample}")

    # key points -------------------------------------------------------
    p_start = nearest_walkable(m, 24, 71) or (24, 71)
    e_start = nearest_walkable(m, 61, 18) or (61, 18)
    key = {"player_spawn": p_start, "enemy_spawn": e_start}
    for i, mine in enumerate(m.mines):
        key[f"mine{i}@({mine['x']},{mine['y']}){'-P' if mine['owner'] == PLAYER else '-E' if mine['owner'] == ENEMY else ''}"] = \
            nearest_walkable(m, mine["x"] + 1, mine["y"] + 2) or (mine["x"], mine["y"])
    for c in m.camps:
        key[f"camp:{c['name']}"] = nearest_walkable(m, c["x"], c["y"]) or (c["x"], c["y"])

    unreachable = [k for k, p in key.items() if p not in main_comp]
    checks["key_points_total"] = len(key)
    checks["key_points_unreachable"] = len(unreachable)
    if unreachable:
        findings.append(f"BLOCKER: key points not reachable: {unreachable}")

    # reachability from each base --------------------------------------
    for side, name, sp in ((PLAYER, "player", p_start), (ENEMY, "enemy", e_start)):
        comp = bfs(m, sp)
        reach = [k for k, p in key.items() if p in comp]
        checks[f"{name}_reaches"] = len(reach)
        checks[f"{name}_reaches_all"] = len(reach) == len(key)
        if len(reach) != len(key):
            miss = [k for k, p in key.items() if p not in comp]
            findings.append(f"{name} base cannot reach: {miss}")

    # route counting ----------------------------------------------------
    ford_tiles = [(i % m.w, i // m.w) for i, v in enumerate(m.ford) if v]
    ramp_tiles = [(i % m.w, i // m.w) for i, v in enumerate(m.ramp) if v]
    # group into connected clusters
    def clusters(tiles):
        s = set(tiles)
        out = []
        while s:
            seed = s.pop()
            q = deque([seed])
            grp = {seed}
            while q:
                x, y = q.popleft()
                for dx, dy in DIRS:
                    n = (x + dx, y + dy)
                    if n in s:
                        s.discard(n)
                        grp.add(n)
                        q.append(n)
            out.append(grp)
        return out

    ford_groups = clusters(ford_tiles)
    ramp_groups = clusters(ramp_tiles)
    checks["ford_clusters"] = len(ford_groups)
    checks["ford_tiles"] = len(ford_tiles)
    checks["ramp_clusters"] = len(ramp_groups)
    checks["ramp_tiles"] = len(ramp_tiles)
    crossings = len(ford_groups) + len(ramp_groups)
    checks["total_crossings"] = crossings
    if crossings < 3:
        findings.append(f"ROUTE: only {crossings} crossing cluster(s) between the halves "
                        "(want >=3: two fords + plateau ramp, plus the goat path)")
    for g in ford_groups:
        if len(g) < 3:
            findings.append(f"ROUTE: a ford cluster is only {len(g)} tiles wide: {sorted(g)[:6]}")

    # distances / fairness ---------------------------------------------
    p_home = next((key[k] for k in key if k.startswith("mine") and k.endswith("-P")), None)
    e_home = next((key[k] for k in key if k.startswith("mine") and k.endswith("-E")), None)
    d = {}
    d["player->own_mine"] = path_len(m, p_start, p_home)
    d["enemy->own_mine"] = path_len(m, e_start, e_home)
    d["player->enemy_ramp"] = path_len(m, p_start, nearest_walkable(m, 64, 30))
    d["enemy->player_approach"] = path_len(m, e_start, nearest_walkable(m, 26, 66))
    d["player->nearest_neutral"] = min(
        (path_len(m, p_start, key[k]) for k in key
         if k.startswith("mine") and not k.endswith(("-P", "-E")) and path_len(m, p_start, key[k])),
        default=None)
    d["enemy->nearest_neutral"] = min(
        (path_len(m, e_start, key[k]) for k in key
         if k.startswith("mine") and not k.endswith(("-P", "-E")) and path_len(m, e_start, key[k])),
        default=None)
    checks["path_lengths"] = d
    if d["player->own_mine"] and d["enemy->own_mine"]:
        ratio = max(d["player->own_mine"], d["enemy->own_mine"]) / max(
            1e-6, min(d["player->own_mine"], d["enemy->own_mine"]))
        checks["home_mine_distance_ratio"] = round(ratio, 2)
        if ratio > 1.35:
            findings.append(f"FAIRNESS: home mine distance ratio {ratio} (>1.35)")

    # local resources ----------------------------------------------------
    wood_p = near(m, *p_start, 14, lambda x, y: (x, y) in m.wood)
    wood_e = near(m, *e_start, 14, lambda x, y: (x, y) in m.wood)
    checks["wood_near_player"] = wood_p
    checks["wood_near_enemy"] = wood_e
    if wood_p and wood_e and (max(wood_p, wood_e) / max(1, min(wood_p, wood_e))) > 1.6:
        findings.append(f"FAIRNESS: wood near halls {wood_p} vs {wood_e} (>1.6x)")

    build_p = near(m, *p_start, 10, lambda x, y: walkable(m, x, y) and m.clear[m.i(x, y)])
    build_e = near(m, *e_start, 10, lambda x, y: walkable(m, x, y) and m.clear[m.i(x, y)])
    checks["clear_tiles_player_r10"] = build_p
    checks["clear_tiles_enemy_r10"] = build_e
    if min(build_p, build_e) < 40:
        findings.append(f"BUILD: only {min(build_p, build_e)} clear tiles within r10 of a hall "
                        "(need room for a base)")

    # camps / economy ----------------------------------------------------
    checks["mines"] = [dict(x=mm["x"], y=mm["y"], gold=mm["gold"], owner=mm["owner"])
                       for mm in m.mines]
    checks["camps"] = [dict(x=c["x"], y=c["y"], name=c["name"], units=len(c["units"]))
                       for c in m.camps]

    checks["findings"] = findings
    checks["verdict"] = "FAIL" if any(f.startswith(("BLOCKER",)) for f in findings) else (
        "WARN" if findings else "PASS")

    if args.json:
        print(json.dumps(checks))
        return 0

    lines = ["# map-audit-01 — Ashen Vale structural audit", "",
             f"Generated from the game's own `generate_map()` by mimo. "
             f"Verdict: **{checks['verdict']}** ({len(findings)} findings)", ""]
    lines.append("## Checks")
    lines.append("")
    lines.append("| check | value |")
    lines.append("|---|---|")
    for k, v in checks.items():
        if k in ("findings", "verdict", "mines", "camps"):
            continue
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("## Mines")
    lines.append("")
    for mm in checks["mines"]:
        side = {PLAYER: "player", ENEMY: "enemy"}.get(mm["owner"], "neutral")
        lines.append(f"- ({mm['x']},{mm['y']}) {mm['gold']}g — {side}")
    lines.append("")
    lines.append("## Camps")
    lines.append("")
    for c in checks["camps"]:
        lines.append(f"- {c['name']} @ ({c['x']},{c['y']}) — {c['units']} units")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if findings:
        for f in findings:
            lines.append(f"- {f}")
    else:
        lines.append("- none — structure is sound")
    lines.append("")
    text = "\n".join(lines)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f'{{"qa": {json.dumps({"map_audit": checks["verdict"], "findings": len(findings)})}}}')
    print(f"wrote {args.out}")
    for f in findings:
        print(" -", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
