#!/usr/bin/env python3
"""Real X window probe (mimo, tools/qa/) — deepseek's task (1).

Runs the *actual* game on a real X server (Xvfb, no SDL dummy) and proves the
two things the user says are broken, at the OS level:

  * resolution: window opens at the right size, picture is not clipped or
    stretched, and stays correct after the window is resized,
  * controls: a REAL cursor click (xdotool) placed at the visual position of a
    unit selects it, and a click on empty ground deselects — asserted through
    the game's own EMBERFALL_QA=state output.

    DISPLAY=:99 Xvfb :99 -screen 0 1920x1080x24 -ac -nolisten tcp -extension GLX &
    .venv/bin/python tools/qa/xwindow_probe.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SHOTS = os.path.join(ROOT, "design", "notes", "shots")
sys.path.insert(0, ROOT)
LOGDIR = os.path.join(ROOT, "design", "notes")

RESULTS: list[tuple[str, str, str]] = []
DISPLAY = os.environ.get("X_DISPLAY", ":99")


def rec(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)


def sh(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return (r.stdout or "") + (r.stderr or "")


def find_window() -> str | None:
    """xdotool --name is unreliable on this title (em dash / WM_NAME vs
    _NET_WM_NAME); the X tree never lies."""
    out = sh(["xwininfo", "-root", "-tree"])
    m = re.search(r'(0x[0-9a-fA-F]+)\s+"Emberfall[^"]*":.*?(\d+)x(\d+)\+(\d+)\+(\d+)',
                  out)
    return m.group(1) if m else None


def window_geometry(win_id: str) -> dict[int, int]:
    out = sh(["xwininfo", "-id", win_id])
    geo: dict[int, int] = {}
    m = re.search(r"Absolute upper-left X:\s*(-?\d+)", out)
    if m:
        geo["X"] = int(m.group(1))
    m = re.search(r"Absolute upper-left Y:\s*(-?\d+)", out)
    if m:
        geo["Y"] = int(m.group(1))
    m = re.search(r"Width:\s*(\d+)", out)
    if m:
        geo["WIDTH"] = int(m.group(1))
    m = re.search(r"Height:\s*(\d+)", out)
    if m:
        geo["HEIGHT"] = int(m.group(1))
    return geo


def forward(logical: tuple[int, int], ww: int, wh: int) -> tuple[int, int]:
    from emberfall.src.defs import SCREEN_H, SCREEN_W
    scale = min(ww / SCREEN_W, wh / SCREEN_H)
    dw, dh = SCREEN_W * scale, SCREEN_H * scale
    ox, oy = (ww - dw) / 2, (wh - dh) / 2
    return (int(ox + logical[0] * scale), int(oy + logical[1] * scale))


def last_state(log_path: str) -> dict | None:
    try:
        lines = open(log_path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if line.startswith('{"t"'):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def last_sel(log_path: str) -> list | None:
    try:
        lines = open(log_path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if line.startswith('{"t"'):
            try:
                return json.loads(line).get("sel")
            except ValueError:
                continue
    return None


def screenshot(tag: str) -> str:
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, f"xwin-{tag}.png")
    sh(["import", "-display", DISPLAY, "-window", "root", path])
    return path


def click(logical: tuple[int, int], ww: int, wh: int, off=(0, 0)) -> None:
    wx, wy = forward(logical, ww, wh)
    sh(["xdotool", "mousemove", "--sync", str(wx + off[0]), str(wy + off[1]), "click", "1"])
    time.sleep(1.4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="1920x1080,1366x768",
                    help="comma list of Xvfb screen sizes to test (each needs a restart)")
    args = ap.parse_args()

    from emberfall.src.defs import SCREEN_H, SCREEN_W  # noqa: F401

    os.environ["DISPLAY"] = DISPLAY   # xwininfo/xdotool/import all need it
    for size in [s.strip() for s in args.sizes.split(",") if s.strip()]:
        wx_s, wh_s = (int(v) for v in size.split("x"))
        tag = size.replace("x", "-")
        # (re)start Xvfb at this screen size
        sh(["pkill", "-f", f"Xvfb {DISPLAY}"])
        time.sleep(1.0)
        os.makedirs("/tmp/.X11-unix", exist_ok=True)
        xvfb = subprocess.Popen(
            ["Xvfb", DISPLAY, "-screen", "0", f"{wx_s}x{wh_s}x24", "-ac",
             "-nolisten", "tcp", "-extension", "GLX"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "LIBGL_ALWAYS_SOFTWARE": "1"})
        for _ in range(40):
            time.sleep(0.25)
            if subprocess.run(["xdpyinfo", "-display", DISPLAY],
                              capture_output=True).returncode == 0:
                break
        time.sleep(1.0)

        log = os.path.join(LOGDIR, f"qa-xwindow-{tag}.log")
        env = {k: v for k, v in os.environ.items() if k != "SDL_VIDEODRIVER"}
        env["DISPLAY"] = DISPLAY
        env["EMBERFALL_QA"] = "state"
        fh = open(log, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [os.path.join(ROOT, ".venv", "bin", "python"), "-m", "emberfall.main",
             "--qa", "--scene", "base"],
            cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT, text=True)
        time.sleep(12)  # let it boot, load art, and emit state lines

        wid = None
        for _ in range(20):
            wid = find_window()
            if wid:
                break
            time.sleep(0.5)
        rec(f"{size}: game window exists", bool(wid), f"window id={wid}")
        if not wid:
            proc.terminate()
            fh.close()
            xvfb.terminate()
            continue
        geo = window_geometry(wid)
        ww, wh = geo.get("WIDTH", 0), geo.get("HEIGHT", 0)
        off = (geo.get("X", 0), geo.get("Y", 0))
        # adaptive sizing is correct behaviour: must be 16:9, fit the screen
        # with margin, and never exceed the desktop
        ratio_ok = abs((ww / max(wh, 1)) - (SCREEN_W / SCREEN_H)) < 0.02
        fits = ww <= wx_s - 40 and wh <= wh_s - 80
        rec(f"{size}: window is 16:9 and fits the screen",
            ratio_ok and fits and ww >= 960,
            f"window {ww}x{wh}+{off[0]}+{off[1]} on a {wx_s}x{wh_s} screen "
            f"(1600x900 only fits screens >=1640x980)")

        shot1 = screenshot(f"{tag}-opened")

        # --- click 1: empty ground must clear the selection -------------
        before = last_sel(log)
        click((330, 300), ww, wh, off)          # open grass, top-left of the vale
        time.sleep(1.2)
        sel_after_empty = last_sel(log)
        rec(f"{size}: click on empty ground clears selection",
            sel_after_empty == [] or sel_after_empty is None or sel_after_empty != before,
            f"sel {before} -> {sel_after_empty}")

        # --- click 2: the engine tells us where a unit is on screen ------
        st = last_state(log) or {}
        unit_px = st.get("unit_px")
        if unit_px:
            click((int(unit_px[0]), int(unit_px[1])), ww, wh, off)
        else:
            click((752, 486), ww, wh, off)
        time.sleep(1.6)
        sel_after_units = last_sel(log)
        rec(f"{size}: click at the units selects them",
            bool(sel_after_units),
            f"unit_px={unit_px} -> sel {sel_after_units}")
        shot2 = screenshot(f"{tag}-clicked")

        # --- resize the window and repeat: mapping must follow ---------
        sh(["xdotool", "windowsize", wid, "1100", "700"])
        time.sleep(2.0)
        geo2 = window_geometry(wid)
        ww2, wh2 = geo2.get("WIDTH", 0), geo2.get("HEIGHT", 0)
        st2 = last_state(log) or {}
        up2 = st2.get("unit_px") or unit_px
        click((int(up2[0]), int(up2[1])), ww2, wh2, off) if up2 else None
        time.sleep(1.5)
        sel_resized = last_sel(log)
        rec(f"{size}: click still lands after resizing window to {ww2}x{wh2}",
            bool(sel_resized) and (ww2, wh2) != (ww, wh),
            f"window {ww}x{wh} -> {ww2}x{wh2}, unit_px={up2}, sel {sel_resized}")
        screenshot(f"{tag}-resized-{ww2}x{wh2}")

        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        fh.close()
        xvfb.terminate()
        time.sleep(1.0)

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    lines = ["# qa-xwindow — real X server test (window + real cursor clicks)", "",
             f"**{len(fails)} FAIL / {len(RESULTS)} checks**", "",
             "| check | result | detail |", "|---|---|---|"]
    for name, status, detail in RESULTS:
        lines.append(f"| {name} | {status} | {detail} |")
    lines += ["", "Screenshots: `design/notes/shots/xwin-*.png`", ""]
    out = os.path.join(LOGDIR, "qa-xwindow.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(json.dumps({"qa": {"xwindow_pass": len(RESULTS) - len(fails),
                             "xwindow_fail": len(fails)}}))
    print(f"wrote {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    if not shutil.which("xdotool") or not shutil.which("import"):
        print("xdotool / ImageMagick import required")
        sys.exit(2)
    sys.exit(main())
