#!/usr/bin/env python3
"""Emberfall QA harness (mimo, owns tools/qa/).

Runs the native pygame build on a virtual X display, screenshots it on a
schedule, measures the real frame cadence, drives scripted input, and writes a
report stub into design/notes/.

    python3 tools/qa/run_qa.py                     # boot check + screenshots
    python3 tools/qa/run_qa.py --label qa-01       # names the report
    python3 tools/qa/run_qa.py --input tools/qa/scripts/smoke.json
    python3 tools/qa/run_qa.py --cmd ".venv/bin/python -m emberfall"

Everything it needs is configurable because the engine entry point is owned by
deepseek and may move; defaults try the common candidates.

Exit codes: 0 = run healthy, 1 = process died / never booted, 2 = setup error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SHOTS = os.path.join(ROOT, "design", "notes", "shots")
NOTES = os.path.join(ROOT, "design", "notes")
DISPLAY = ":99"
SCREEN = "1600x900x24"

ENTRY_CANDIDATES = [
    ".venv/bin/python -m emberfall",
    ".venv/bin/python emberfall/main.py",
    ".venv/bin/python emberfall/run.py",
    "python3 emberfall/main.py",
]


def log(msg: str) -> None:
    print(f"[qa] {msg}", flush=True)


def resolve_cmd(explicit: str | None) -> str:
    if explicit:
        return explicit
    for cand in ENTRY_CANDIDATES:
        exe = cand.split()[0]
        path = os.path.join(ROOT, exe)
        if not os.path.exists(path):
            continue
        rest = cand.split(maxsplit=1)[1]
        # a module target must exist as a package
        if rest.startswith("-m "):
            pkg = rest[3:].replace(".", "/")
            if not os.path.isdir(os.path.join(ROOT, pkg)):
                continue
        elif not os.path.exists(os.path.join(ROOT, rest)):
            continue
        return cand
    return ""


def ensure_display() -> subprocess.Popen | None:
    """Start Xvfb if DISPLAY is not already usable. Returns the Popen (or None)."""
    if os.environ.get("QA_EXTERNAL_DISPLAY"):
        return None
    probe = subprocess.run(
        ["xdpyinfo", "-display", DISPLAY], capture_output=True, text=True
    )
    if probe.returncode == 0:
        return None
    # Xvfb refuses to create its socket dir unless it already exists (euid != 0),
    # and in a sandboxed /tmp it will not exist. Make it first.
    sockdir = "/tmp/.X11-unix"
    os.makedirs(sockdir, exist_ok=True)
    try:
        os.chmod(sockdir, 0o1777)
    except OSError:
        pass
    log(f"starting Xvfb on {DISPLAY} ({SCREEN})")
    proc = subprocess.Popen(
        # -extension GLX is required here: the GLX probe loads nvidia's EGL
        # driver and segfaults inside the sandbox, aborting the whole server.
        ["Xvfb", DISPLAY, "-screen", "0", SCREEN, "-ac", "-nolisten", "tcp",
         "-extension", "GLX"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "LIBGL_ALWAYS_SOFTWARE": "1"},
    )
    for _ in range(40):  # wait for readiness instead of racing it
        time.sleep(0.25)
        if proc.poll() is not None:
            log(f"Xvfb exited rc={proc.returncode}")
            return None
        r = subprocess.run(["xdpyinfo", "-display", DISPLAY], capture_output=True)
        if r.returncode == 0:
            log("display ready")
            return proc
    log("Xvfb not ready after 10s; continuing anyway")
    return proc


def shot(tag: str) -> str | None:
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, f"{tag}.png")
    r = subprocess.run(
        ["import", "-display", DISPLAY, "-window", "root", path],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not os.path.exists(path):
        log(f"screen capture failed: {r.stderr.strip()[:200]}")
        return None
    return path


def measure_fps(seconds: float = 5.0) -> tuple[float, int, int]:
    """Capture the screen for `seconds` and count distinct frames.

    ffmpeg grabs at 30 fps; mpdecimate drops near-identical frames, so
    unique_frames / seconds approximates the game's real update rate
    (capped by our 30 fps grab — report both numbers).
    """
    os.makedirs(SHOTS, exist_ok=True)
    out = os.path.join(SHOTS, "fpsprobe.mkv")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info", "-y",
        "-f", "x11grab", "-framerate", "30", "-video_size", "1600x900",
        "-t", f"{seconds}", "-i", DISPLAY + ".0",
        "-vf", "mpdecimate=hi=64*12:lo=64*5:frac=0.05",
        "-vsync", "vfr", out,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(out):
        return -1.0, 0, 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", out],
        capture_output=True, text=True,
    )
    try:
        uniq = int(probe.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        uniq = -1
    os.unlink(out)
    grabbed = int(round(seconds * 30))
    return (uniq / seconds if uniq >= 0 else -1.0), uniq, grabbed


def send_input(script: str) -> None:
    """Drive xdotool from a json script:
    [{"wait": 1.0}, {"key": "a"}, {"click": 1, "x": 400, "y": 300},
     {"drag": [800, 400, 1000, 600]}, {"type": "hello"}]
    """
    if not os.path.exists(script):
        log(f"input script missing: {script}")
        return
    steps = json.loads(open(script, encoding="utf-8").read())
    for i, step in enumerate(steps):
        if "wait" in step:
            time.sleep(float(step["wait"]))
        elif "key" in step:
            subprocess.run(["xdotool", "key", "--clearmodifiers", str(step["key"])])
        elif "text" in step:
            subprocess.run(["xdotool", "type", "--clearmodifiers", str(step["text"])])
        elif "click" in step:
            subprocess.run(
                ["xdotool", "mousemove", str(step.get("x", 800)), str(step.get("y", 450)),
                 "click", "--repeat", str(step.get("repeat", 1)), str(step["click"])]
            )
        elif "drag" in step:
            x1, y1, x2, y2 = step["drag"]
            subprocess.run(
                ["xdotool", "mousemove", str(x1), str(y1), "mousedown",
                 str(step.get("button", 1)), "mousemove", str(x2), str(y2),
                 "mouseup", str(step.get("button", 1))], check=False)
        elif "shot" in step:
            shot(str(step["shot"]))
        log(f"step {i}: {step}")


def extract_state(log_text: str) -> list[dict]:
    """Pull JSON state lines the game prints ({"qa":...} or its {"t":...} form)."""
    found = []
    for line in log_text.splitlines():
        line = line.strip()
        if not (line.startswith("{") and ("fps" in line or '"qa"' in line)):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj:
            found.append(obj)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cmd", default=None, help="command to launch the game")
    ap.add_argument("--label", default=None, help="report/shot label (default qa-<ts>)")
    ap.add_argument("--input", default=None, help="json input script")
    ap.add_argument("--shots", default="2,10,30,60", help="comma seconds for screenshots")
    ap.add_argument("--fps-probe", type=float, default=5.0, help="seconds for fps capture (0=skip)")
    ap.add_argument("--run-seconds", type=float, default=75.0, help="total run time")
    ap.add_argument("--env", action="append", default=[], help="EXTRA=VAL for the game")
    ap.add_argument("--x11", action="store_true",
                    help="use Xvfb + screen grabs instead of the headless default")
    ap.add_argument("--shot-dir", default=None,
                    help="dir where the game writes its own PNGs (default design/notes/shots)")
    args = ap.parse_args()

    headless = not args.x11

    label = args.label or f"qa-{time.strftime('%m%d-%H%M%S')}"
    cmd_str = resolve_cmd(args.cmd)
    if not cmd_str:
        log("no entry point found; pass --cmd")
        for c in ENTRY_CANDIDATES:
            log(f"  tried: {c}")
        return 2
    log(f"entry: {cmd_str}")

    os.makedirs(NOTES, exist_ok=True)
    shot_dir = args.shot_dir or SHOTS
    os.makedirs(shot_dir, exist_ok=True)
    baseline_shots = set(os.listdir(shot_dir))
    xfvb = ensure_display() if not headless else None
    env = dict(os.environ)
    if headless:
        # user rule: always headless — the game renders offscreen and saves PNGs
        env["SDL_VIDEODRIVER"] = "dummy"
        env["SDL_AUDIODRIVER"] = "dummy"
    else:
        env["DISPLAY"] = DISPLAY
        env.setdefault("SDL_VIDEODRIVER", "x11")
    env["EMBERFALL_QA"] = args.env[0] if args.env else "1"
    for kv in args.env[1:]:
        k, _, v = kv.partition("=")
        env[k] = v
    log(f"mode: {'headless (SDL dummy)' if headless else 'x11 ' + DISPLAY}")

    log_path = os.path.join(NOTES, f"{label}-run.log")
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            shlex.split(cmd_str), cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            preexec_fn=os.setsid,
        )
        log(f"pid {proc.pid}, logging to {log_path}")
        if proc.stdout is not None:
            os.set_blocking(proc.stdout.fileno(), False)

        shots_times = [float(x) for x in args.shots.split(",") if x.strip()]
        captured: list[tuple[float, str]] = []
        stdout_tail: list[str] = []
        next_shot_idx = 0
        fps_result = None
        fps_done = False
        input_started = False
        deadline = t0 + args.run_seconds

        while time.time() < deadline:
            elapsed = time.time() - t0
            if proc.poll() is not None:
                log(f"process exited rc={proc.returncode} after {elapsed:.1f}s")
                break
            if headless:
                # the game is expected to drop its own PNGs into shot_dir
                now_shots = set(os.listdir(shot_dir)) - baseline_shots
                for name in sorted(now_shots):
                    if name.endswith(".png"):
                        src = os.path.join(shot_dir, name)
                        dst = os.path.join(SHOTS, f"{label}-{name}")
                        if os.path.abspath(src) != os.path.abspath(dst) and os.path.exists(src):
                            try:
                                os.makedirs(SHOTS, exist_ok=True)
                                with open(src, "rb") as fi, open(dst, "wb") as fo:
                                    fo.write(fi.read())
                                baseline_shots.add(name)
                                captured.append((round(elapsed, 1), dst))
                                log(f"game shot -> {dst}")
                            except OSError as exc:
                                log(f"shot copy failed: {exc}")
            elif next_shot_idx < len(shots_times) and elapsed >= shots_times[next_shot_idx]:
                p = shot(f"{label}-t{int(shots_times[next_shot_idx])}")
                if p:
                    captured.append((shots_times[next_shot_idx], p))
                    log(f"shot -> {p}")
                next_shot_idx += 1
            if not headless and not fps_done and elapsed >= max(shots_times, default=0) + 2:
                # fps probe while the game is live
                if args.fps_probe > 0:
                    log("probing frame cadence...")
                    fps_result = measure_fps(args.fps_probe)
                    log(f"fps probe: {fps_result}")
                fps_done = True
            if (not headless and args.input and not input_started
                    and elapsed >= max(shots_times, default=0) + 4):
                log("driving input script")
                send_input(args.input)
                input_started = True
                p = shot(f"{label}-after-input")
                if p:
                    captured.append((elapsed, p))
            # drain stdout without ever blocking the capture loop
            if proc.stdout is not None:
                try:
                    chunk = proc.stdout.read()
                except (BlockingIOError, ValueError, OSError):
                    chunk = None
                if chunk:
                    for line in chunk.splitlines(keepends=True):
                        stdout_tail.append(line)
                        logf.write(line)
                    if len(stdout_tail) > 400:
                        del stdout_tail[:-400]
                else:
                    time.sleep(0.1)
            else:
                time.sleep(0.2)

        alive = proc.poll() is None
        if alive:
            log("stopping game process")
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass

    log_text = "".join(stdout_tail) + open(log_path, encoding="utf-8", errors="replace").read()
    crashed = bool(re.search(r"Traceback \(most recent call last\)", log_text))
    states = extract_state(log_text)

    report = os.path.join(NOTES, f"{label}.md")
    with open(report, "w", encoding="utf-8") as fh:
        fh.write(f"# {label} — automated QA run\n\n")
        fh.write(f"- when: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        fh.write(f"- command: `{cmd_str}`\n")
        fh.write(f"- duration: {time.time() - t0:.1f}s, exited by harness: {not alive}\n")
        fh.write(f"- traceback in log: {'YES — BUG' if crashed else 'no'}\n")
        if fps_result and fps_result[0] >= 0:
            fh.write(f"- frame cadence: {fps_result[0]:.1f} distinct fps "
                     f"({fps_result[1]} unique / {fps_result[2]} grabbed)\n")
        fh.write("\n## screenshots\n\n")
        for t, p in captured:
            rel = os.path.relpath(p, ROOT)
            fh.write(f"- t≈{t}s: ![{rel}]({rel})\n")
        if states:
            fh.write("\n## state samples\n\n```json\n")
            for s in states[-20:]:
                fh.write(json.dumps(s) + "\n")
            fh.write("```\n")
        fh.write(f"\n## log\n\nsee `{os.path.relpath(log_path, ROOT)}`\n")
    log(f"report -> {report}")

    if xfvb:
        xfvb.terminate()
    if crashed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
