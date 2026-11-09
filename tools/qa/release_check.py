#!/usr/bin/env python3
"""Release gate for the Emberfall beta (mimo, tools/qa/).

Objective pass/fail for everything that does not need a human eyeball:
asset contract completeness, decode-ability, licensing, docs, map structure,
and (optionally) a headless boot of the actual game.

    python3 tools/qa/release_check.py                 # static checks, fast
    python3 tools/qa/release_check.py --boot           # + headless boot probe
    python3 tools/qa/release_check.py --gate beta      # non-zero exit if any FAIL

Writes design/notes/release-check.md and prints {"qa": ...} for run_qa.py.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

SFX = ["click", "select", "command", "error", "sword", "bow", "magic", "holy",
       "build", "build-done", "gold", "chop", "death", "level-up", "alert",
       "horn", "explosion", "roar", "victory", "defeat"]
MUSIC = ["menu", "battle", "night"]
ICONS = ["worker", "footman", "archer", "knight", "priest", "ballista",
         "townhall", "farm", "barracks", "mill", "blacksmith", "sanctum",
         "tower", "altar", "keep", "gold", "lumber", "food",
         "ember-lance", "aegis", "consecrate", "daybreak"]
ENTRY = ".venv/bin/python -m emberfall.main"


def check_audio(results: list[tuple[str, str, str]]) -> None:
    for name in SFX:
        p = os.path.join(ROOT, "assets", "audio", "sfx", f"{name}.ogg")
        if not os.path.exists(p):
            results.append((f"audio:sfx/{name}", "FAIL", "missing"))
            continue
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "stream=codec_name,sample_rate,channels",
                            "-of", "csv=p=0", p], capture_output=True, text=True)
        out = r.stdout.strip()
        if "vorbis" not in out:
            results.append((f"audio:sfx/{name}", "FAIL", f"ffprobe: {out[:60]}"))
        elif os.path.getsize(p) < 1000:
            results.append((f"audio:sfx/{name}", "FAIL", "suspiciously small"))
        else:
            results.append((f"audio:sfx/{name}", "PASS", out.replace("\n", " ")))
    for name in MUSIC:
        p = os.path.join(ROOT, "assets", "audio", "music", f"{name}.ogg")
        if not os.path.exists(p):
            results.append((f"audio:music/{name}", "FAIL", "missing"))
            continue
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", p],
                           capture_output=True, text=True)
        try:
            dur = float(r.stdout.strip().splitlines()[0])
        except (ValueError, IndexError):
            results.append((f"audio:music/{name}", "FAIL", "undecodable"))
            continue
        lo, hi = (90.0, 120.0) if name == "battle" else (60.0, 90.0)
        ok = lo <= dur <= hi
        results.append((f"audio:music/{name}", "PASS" if ok else "FAIL",
                        f"{dur:.1f}s (want {lo:.0f}-{hi:.0f}s)"))


def check_sdl_load(results: list[tuple[str, str, str]]) -> None:
    """Every shipped sound must load through the engine's actual loader."""
    script = (
        "import pygame,glob,os,sys,json\n"
        "pygame.init(); pygame.mixer.init(44100)\n"
        "bad=[]\n"
        "for f in sorted(glob.glob('assets/audio/**/*.ogg',recursive=True)):\n"
        "    if '_gen' in f: continue\n"
        "    try:\n"
        "        s=pygame.mixer.Sound(f)\n"
        "        if s.get_length()<0.05: bad.append((f,'too short'))\n"
        "    except Exception as e: bad.append((f,str(e)))\n"
        "print(json.dumps({'bad':bad,'total':len(glob.glob('assets/audio/**/*.ogg',recursive=True))}))\n"
    )
    r = subprocess.run([os.path.join(ROOT, ".venv", "bin", "python"), "-c", script],
                       cwd=ROOT, capture_output=True, text=True,
                       env={**os.environ, "SDL_AUDIODRIVER": "dummy",
                            "SDL_VIDEODRIVER": "dummy"})
    try:
        data = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        results.append(("audio:SDL load", "FAIL", (r.stderr or r.stdout)[:120]))
        return
    if data["bad"]:
        results.append(("audio:SDL load", "FAIL", str(data["bad"])[:160]))
    else:
        results.append(("audio:SDL load", "PASS", f"{data['total']} files load"))


def check_icons(results: list[tuple[str, str, str]]) -> None:
    missing = [i for i in ICONS
               if not os.path.exists(os.path.join(ROOT, "assets", "icons", f"icon-{i}.svg"))]
    png_missing = [i for i in ICONS
                   if not os.path.exists(os.path.join(ROOT, "assets", "icons", "png",
                                                      f"icon-{i}.png"))]
    results.append(("icons:svg contract", "PASS" if not missing else "FAIL",
                    "all present" if not missing else f"missing {missing}"))
    results.append(("icons:png runtime", "PASS" if not png_missing else "WARN",
                    "all present" if not png_missing else f"missing {len(png_missing)} "
                    "(engine may rasterize on the fly)"))


def check_buildings(results: list[tuple[str, str, str]]) -> None:
    d = os.path.join(ROOT, "assets", "flare", "buildings")
    if not os.path.isdir(d):
        results.append(("art:flare buildings", "FAIL", "directory missing"))
    else:
        pngs = [f for f in os.listdir(d) if f.endswith(".png")]
        results.append(("art:flare buildings", "PASS" if len(pngs) >= 14 else "WARN",
                        f"{len(pngs)} sprites (want >=14)"))
    for name in ("design/notes/flare-buildings.md", "LICENSES-FLARE.md",
                 "design/notes/flare-import.md"):
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            results.append((f"doc:{name}", "FAIL", "missing"))
        else:
            txt = open(p, encoding="utf-8", errors="replace").read()
            results.append((f"doc:{name}", "PASS", f"{len(txt.splitlines())} lines"))


def check_license(results: list[tuple[str, str, str]]) -> None:
    p = os.path.join(ROOT, "LICENSES-FLARE.md")
    if not os.path.exists(p):
        results.append(("license:flare", "FAIL", "LICENSES-FLARE.md missing"))
        return
    txt = open(p, encoding="utf-8", errors="replace").read().lower()
    need = {
        "license name (CC BY-SA 3.0)": ("cc-by-sa" in txt) or ("cc by-sa" in txt)
        or ("cc by sa" in txt),
        "author credit (Bellanger)": "bellanger" in txt,
        "canonical license URL": "creativecommons.org/licenses/by-sa/3.0" in txt,
        "source repository": "github.com/flareteam/flare-game" in txt,
    }
    missing = [k for k, ok in need.items() if not ok]
    results.append(("license:flare", "PASS" if not missing else "FAIL",
                    "attribution complete" if not missing else f"missing {missing}"))


def check_docs(results: list[tuple[str, str, str]]) -> None:
    for name in ("design/DESIGN.md", "design/COLLAB.md", "design/ASSET-CONTRACT.md",
                 "collaboration.md"):
        p = os.path.join(ROOT, name)
        results.append((f"doc:{name}", "PASS" if os.path.exists(p) else "FAIL",
                        "present" if os.path.exists(p) else "missing"))
    readme = os.path.join(ROOT, "README.md")
    if os.path.exists(readme):
        txt = open(readme, encoding="utf-8", errors="replace").read()
        has_run = bool(re.search(r"(venv/bin/python|emberfall)", txt))
        results.append(("doc:README run instructions", "PASS" if has_run else "FAIL",
                        "mentions the run command" if has_run else
                        "still the broker README — no game run instructions"))


def check_map(results: list[tuple[str, str, str]]) -> None:
    r = subprocess.run([os.path.join(ROOT, ".venv", "bin", "python"),
                        os.path.join(HERE, "map_audit.py"), "--json"],
                       cwd=ROOT, capture_output=True, text=True, timeout=180)
    try:
        data = json.loads(r.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        results.append(("map:audit", "FAIL", (r.stderr or r.stdout)[:120]))
        return
    verdict = data.get("verdict", "?")
    results.append(("map:audit", "PASS" if verdict == "PASS" else "FAIL",
                    f"{verdict}: {len(data.get('findings', []))} findings"))
    for f in data.get("findings", [])[:6]:
        results.append((f"map:finding", "FAIL" if f.startswith("BLOCKER") else "WARN", f))


def check_boot(results: list[tuple[str, str, str]], seconds: float = 25.0) -> None:
    entry_py = os.path.join(ROOT, "emberfall", "main.py")
    pkg = os.path.join(ROOT, "emberfall", "__init__.py")
    if not os.path.exists(entry_py) and not os.path.exists(pkg):
        results.append(("boot:entry", "FAIL", "emberfall/main.py does not exist yet"))
        return
    env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
           "EMBERFALL_QA": "state", "PYTHONUNBUFFERED": "1"}
    out_log = os.path.join(ROOT, "design", "notes", "boot-probe.log")
    t0 = time.time()
    with open(out_log, "w", encoding="utf-8") as fh:
        try:
            proc = subprocess.Popen(ENTRY.split(), cwd=ROOT, env=env,
                                    stdout=fh, stderr=subprocess.STDOUT)
            try:
                rc = proc.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    rc = proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    rc = None
        except FileNotFoundError as exc:
            results.append(("boot:entry", "FAIL", str(exc)))
            return
    log = open(out_log, encoding="utf-8", errors="replace").read()
    crashed = "Traceback (most recent call last)" in log
    results.append(("boot:headless", "FAIL" if crashed else "PASS",
                    f"crashed after {time.time()-t0:.1f}s" if crashed
                    else f"alive {seconds:.0f}s, rc={rc}"))
    states = len(re.findall(r'\{"(?:qa|t)":', log))
    results.append(("boot:state stream", "PASS" if states else "WARN",
                    f"{states} state lines"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", action="store_true", help="also probe a headless boot")
    ap.add_argument("--gate", choices=["beta"], default=None,
                    help="exit non-zero when anything FAILs")
    args = ap.parse_args()

    results: list[tuple[str, str, str]] = []
    check_audio(results)
    check_sdl_load(results)
    check_icons(results)
    check_buildings(results)
    check_license(results)
    check_docs(results)
    check_map(results)
    if args.boot:
        check_boot(results)

    fails = [r for r in results if r[1] == "FAIL"]
    warns = [r for r in results if r[1] == "WARN"]

    lines = [f"# release-check — {time.strftime('%Y-%m-%d %H:%M:%S')}", "",
             f"**{len(fails)} FAIL / {len(warns)} WARN / {len(results)} checks**", "",
             "| check | status | detail |", "|---|---|---|"]
    for name, status, detail in results:
        d = str(detail).replace("|", "/").replace("\n", " ")
        lines.append(f"| {name} | {status} | {d} |")
    lines.append("")
    md = os.path.join(ROOT, "design", "notes", "release-check.md")
    os.makedirs(os.path.dirname(md), exist_ok=True)
    with open(md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(json.dumps({"qa": {"release_fail": len(fails), "release_warn": len(warns),
                             "release_checks": len(results)}}))
    for name, status, detail in results:
        if status != "PASS":
            print(f" {status:4} {name}: {detail}")
    print(f"wrote {md}")
    if args.gate == "beta" and fails:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
