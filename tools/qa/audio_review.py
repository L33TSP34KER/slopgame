#!/usr/bin/env python3
"""Visual + numeric review of the shipped audio (mimo, tools/qa/).

Decodes every OGG under assets/audio/ with ffmpeg, draws a waveform +
spectrogram grid, and reports technical smells a loudness number cannot catch:
DC offset, start/end discontinuities (clicks), over-long tails, spectral holes,
and relative loudness within the pack.

    python3 tools/qa/audio_review.py                 # design/notes/audio-review.png
    python3 tools/qa/audio_review.py --only sfx/magic.ogg,sfx/sword.ogg
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
AUDIO = os.path.join(ROOT, "assets", "audio")
OUT_DIR = os.path.join(ROOT, "design", "notes")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def decode(path: str) -> tuple[np.ndarray, int]:
    """Return (mono float array in [-1,1], sample_rate)."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-f", "f32le", "-"],
        capture_output=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"decode failed: {r.stderr.decode()[:200]}")
    raw = np.frombuffer(r.stdout, dtype=np.float32)
    # ffmpeg does not report rate here; probe it
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=sample_rate", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        sr = int(p.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        sr = 44100
    return raw.astype(np.float32), sr


def stats(x: np.ndarray, sr: int) -> dict:
    eps = 1e-9
    peak = float(np.max(np.abs(x)) + eps)
    rms = float(np.sqrt(np.mean(x ** 2)) + eps)
    dc = float(np.mean(x))
    head_jump = float(abs(x[1] - x[0])) if len(x) > 1 else 0.0
    tail_jump = float(abs(x[-1] - x[-2])) if len(x) > 1 else 0.0
    # click detector: jump at edges relative to body rms
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    centroid = float((freqs * spec).sum() / (spec.sum() + eps))
    energy = spec ** 2
    low = float(energy[freqs < 250].sum() / (energy.sum() + eps))
    high = float(energy[freqs > 6000].sum() / (energy.sum() + eps))
    return {
        "dur": round(len(x) / sr, 3),
        "peak_db": round(20 * np.log10(peak), 2),
        "rms_db": round(20 * np.log10(rms), 2),
        "crest_db": round(20 * np.log10(peak / rms), 2),
        "dc_offset": round(dc, 5),
        "edge_click": round(max(head_jump, tail_jump) / rms, 2),
        "centroid_hz": round(centroid),
        "low_ratio": round(low, 3),
        "high_ratio": round(high, 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="comma paths relative to assets/audio")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "audio-review.png"))
    args = ap.parse_args()

    files = []
    for dirpath, _, names in os.walk(AUDIO):
        if "_gen" in dirpath:
            continue
        for n in sorted(names):
            if n.endswith(".ogg"):
                files.append(os.path.relpath(os.path.join(dirpath, n), AUDIO))
    files.sort()
    if args.only:
        want = {w.strip() for w in args.only.split(",")}
        files = [f for f in files if f in want]
    if not files:
        print("no audio files found")
        return 2

    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []
    n = len(files)
    cols = 4
    nrows = (n + cols - 1) // cols
    fig, axes = plt.subplots(nrows * 2, cols, figsize=(4.6 * cols, 2.1 * nrows))
    axes = np.atleast_2d(axes)

    report = []
    for i, rel in enumerate(files):
        path = os.path.join(AUDIO, rel)
        try:
            x, sr = decode(path)
            st = stats(x, sr)
        except Exception as exc:  # noqa: BLE001
            report.append({"file": rel, "error": str(exc)})
            continue
        st["file"] = rel
        report.append(st)
        r, c = divmod(i, cols)
        axw = axes[r * 2][c]
        axs = axes[r * 2 + 1][c]
        t = np.arange(len(x)) / sr
        axw.plot(t, x, lw=0.5, color="#d9a441")
        axw.set_ylim(-1.05, 1.05)
        axw.set_title(f"{rel}  {st['dur']}s  pk{st['peak_db']}dB", fontsize=8)
        axw.tick_params(labelsize=6)
        # spectrogram (short-time FFT)
        try:
            win = 1024
            hop = max(1, len(x) // 400)
            frames = 1 + max(0, (len(x) - win) // hop)
            if frames > 1 and len(x) > win:
                idx = np.arange(frames)[:, None] * hop + np.arange(win)[None, :]
                seg = x[idx] * np.hanning(win)
                S = np.abs(np.fft.rfft(seg, axis=1)).T
                S_db = 20 * np.log10(S + 1e-6)
                khz = sr / 1000.0
                axs.imshow(S_db, origin="lower", aspect="auto", cmap="magma",
                          extent=[0, t[-1], 0, khz])
                axs.set_ylim(0, min(8.0, khz))
            else:
                axs.text(0.5, 0.5, "too short", ha="center", va="center",
                         transform=axs.transAxes, fontsize=7)
        except Exception:  # noqa: BLE001
            axs.text(0.5, 0.5, "spec fail", ha="center", va="center",
                     transform=axs.transAxes, fontsize=7)
        axs.tick_params(labelsize=6)

    # hide unused axes
    for i in range(n, nrows * cols):
        r, c = divmod(i, cols)
        axes[r * 2][c].axis("off")
        axes[r * 2 + 1][c].axis("off")

    fig.tight_layout()
    fig.savefig(args.out, dpi=110)
    plt.close(fig)

    # pack-level judgement
    peaks = [r["peak_db"] for r in report if "peak_db" in r]
    rmses = [r["rms_db"] for r in report if "rms_db" in r]
    clicks = [(r["file"], r["edge_click"]) for r in report if r.get("edge_click", 0) > 6]
    dc = [(r["file"], r["dc_offset"]) for r in report if abs(r.get("dc_offset", 0)) > 0.002]
    summary = {
        "files": len(report),
        "peak_db_range": [round(min(peaks), 2), round(max(peaks), 2)] if peaks else None,
        "rms_db_range": [round(min(rmses), 2), round(max(rmses), 2)] if rmses else None,
        "loudness_spread_db": round(max(rmses) - min(rmses), 2) if rmses else None,
        "possible_clicks": clicks,
        "dc_offsets": dc,
        "fails": [r["file"] for r in report
                  if r.get("peak_db") is not None
                  and (r["peak_db"] > (-1.0 if r["file"].startswith("music/") else -6.0))],
        "rms_fails": [r["file"] for r in report
                      if r.get("rms_db") is not None and r["file"].startswith("music/")
                      and r["rms_db"] > -18.0],
        "duration_fails": [r["file"] for r in report
                           if r.get("file", "").startswith("music/")
                           and r.get("dur") is not None
                           and not (60.0 <= r["dur"] <= 120.0
                                    if r["file"].endswith("menu.ogg") or r["file"].endswith("night.ogg")
                                    else 90.0 <= r["dur"] <= 120.0)],
    }
    md = ["# audio-review — visual + numeric pass", "",
          f"Montage: `{os.path.relpath(args.out, ROOT)}`", "",
          "| file | dur | peak dB | RMS dB | crest | edge-click | centroid Hz | low | high |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in report:
        if "error" in r:
            md.append(f"| {r['file']} | ERROR: {r['error']} | | | | | | | |")
            continue
        md.append(f"| {r['file']} | {r['dur']} | {r['peak_db']} | {r['rms_db']} | "
                  f"{r['crest_db']} | {r['edge_click']} | {r['centroid_hz']} | "
                  f"{r['low_ratio']} | {r['high_ratio']} |")
    md += ["", "## Flags", ""]
    if summary["possible_clicks"]:
        md.append(f"- edge discontinuity >6× RMS (possible click): {summary['possible_clicks']}")
    if summary["dc_offsets"]:
        md.append(f"- DC offset: {summary['dc_offsets']}")
    if summary["fails"]:
        md.append(f"- over the peak ceiling (SFX -6 dBFS, music -1): {summary['fails']}")
    if summary.get("rms_fails"):
        md.append(f"- music RMS above the -18 dBFS bed limit: {summary['rms_fails']}")
    if summary.get("duration_fails"):
        md.append(f"- music outside its duration spec: {summary['duration_fails']}")
    if summary["loudness_spread_db"] and summary["loudness_spread_db"] > 8:
        md.append(f"- pack loudness spread {summary['loudness_spread_db']} dB — "
                  "some sounds will jump out in a mixed run")
    if not any(summary[k] for k in ("possible_clicks", "dc_offsets", "fails")):
        md.append("- no technical flags")
    md += ["", "Summary:", "", "```json", json.dumps(summary, indent=2), "```", ""]
    with open(os.path.join(OUT_DIR, "audio-review.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))

    print(json.dumps(summary))
    print(f"wrote {args.out} and design/notes/audio-review.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
