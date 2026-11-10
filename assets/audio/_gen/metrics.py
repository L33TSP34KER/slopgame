#!/usr/bin/env python3
"""Before/after metric capture for the SFX pack (evidence for the council).

Measures, per OGG: duration, decoded sample peak, true peak (ffmpeg loudnorm),
RMS, spectral centroid, crest factor (peak/RMS), DC offset, and edge-click
checks (first/last samples faded, no discontinuity).

    python3 assets/audio/_gen/metrics.py                     # markdown table
    python3 assets/audio/_gen/metrics.py --json out.json     # + JSON dump
    python3 assets/audio/_gen/metrics.py --dir assets/audio/sfx
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from dsp import SR, db20, ffprobe, loudnorm_measure, peak_db, read_pcm_f32, rms_db

DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sfx')


def metrics(path):
    x = read_pcm_f32(path)
    if x.ndim > 1:
        x = x.mean(axis=1)
    st = ffprobe(path)
    ln = loudnorm_measure(path) or {}
    tp = float(ln.get('tp', peak_db(x)))
    n = len(x)
    # spectral centroid (Hann-windowed magnitude spectrum)
    w = np.hanning(n)
    spec = np.abs(np.fft.rfft(x * w))
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    centroid = float((freqs * spec).sum() / (spec.sum() + 1e-12))
    pk = peak_db(x)
    r = rms_db(x)
    crest = pk - r
    dc = float(np.mean(x))
    # edge click proxy: single-sample jump at start/end relative to body RMS
    jump = max(abs(float(x[1] - x[0])), abs(float(x[-1] - x[-2]))) if n > 2 else 0.0
    # fade check: first/last 5 ms should ramp from (near) zero
    e = max(ns5ms := int(0.005 * SR), 1)
    head = float(np.max(np.abs(x[:e]))) if n > e else float(np.max(np.abs(x)))
    tail = float(np.max(np.abs(x[-e:]))) if n > e else float(np.max(np.abs(x)))
    return {
        'file': os.path.basename(path),
        'dur': round(st['dur'], 3),
        'peak_db': round(pk, 2),
        'tp_db': round(tp, 2),
        'rms_db': round(r, 2),
        'centroid_hz': round(centroid),
        'crest_db': round(crest, 2),
        'dc': round(dc, 5),
        'edge_jump_over_rms': round(jump / (10 ** (r / 20) + 1e-12), 2),
        'head5ms_db': round(peak_db(x[:e]), 1),
        'tail5ms_db': round(peak_db(x[-e:]), 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=DEFAULT_DIR)
    ap.add_argument('--json', default=None, help='write full metrics JSON here')
    args = ap.parse_args()
    files = sorted(glob.glob(os.path.join(args.dir, '*.ogg')))
    rows = [metrics(p) for p in files]
    print('| file | dur s | peak dB | TP dB | RMS dB | centroid Hz | crest dB |'
          ' DC | edge/rms | head5ms | tail5ms |')
    print('|---|---|---|---|---|---|---|---|---|---|---|')
    for m in rows:
        print(f"| {m['file'][:-4]} | {m['dur']} | {m['peak_db']} | {m['tp_db']} |"
              f" {m['rms_db']} | {m['centroid_hz']} | {m['crest_db']} |"
              f" {m['dc']:+.4f} | {m['edge_jump_over_rms']} |"
              f" {m['head5ms_db']} | {m['tail5ms_db']} |")
    if args.json:
        with open(args.json, 'w') as fh:
            json.dump(rows, fh, indent=1)
        print(f'wrote {args.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
