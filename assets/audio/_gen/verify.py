#!/usr/bin/env python3
"""EMBERFALL audio pack quality gate.

1. ffprobe: codec=vorbis, 44100 Hz, channels, duration within contract spec
2. decoded sample peak + true peak (ffmpeg loudnorm) + RMS + DC offset
3. music: mono-downmix numbers as tools/qa/audio_review.py measures them
4. music loop continuity: raw wrap-around step, 20 ms / 50 ms wrap crossfade
5. non-silence floor
Prints markdown tables; exit code 1 on any failure.
"""
import sys, os, glob, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from dsp import *

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SFX_DUR = {          # max seconds (contract: < 1.2 s unless noted)
    'click': 1.20, 'select': 1.20, 'command': 1.20, 'error': 1.20,
    'sword': 1.20, 'bow': 1.20, 'magic': 1.20, 'holy': 1.20,
    'build': 1.20, 'build-done': 1.20, 'gold': 1.20, 'chop': 1.20,
    'death': 1.20, 'explosion': 1.20,
    'level-up': 1.60, 'alert': 1.60, 'horn': 2.60, 'roar': 2.10,
    'victory': 4.20, 'defeat': 4.20,
}
MUSIC_SPEC = {'menu': (60.0, 90.0), 'battle': (90.0, 120.0), 'night': (60.0, 90.0)}
RMS_FLOOR = -45.0
SFX_PEAK_MAX = -6.0        # dBFS, sample and true peak
MUSIC_TP_MAX = -1.0        # native true peak (contract)
MONO_PEAK_MAX = -1.0       # QA tool gate on the ffmpeg -ac 1 downmix
MONO_RMS_MAX = -18.0       # QA tool gate (music bed <= -18 dBFS)
MONO_RMS_TGT = (-19.0, -18.0)
NATIVE_RMS = (-23.0, -19.0)
DC_MAX = 0.002


def read_mono(path):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1',
                        '-f', 'f32le', '-'], capture_output=True)
    return np.frombuffer(r.stdout, dtype='<f4')


def loop_metrics(path):
    """Wrap-around discontinuity of a music loop.

    step     : max |x[0] - x[N-1]|, i.e. the single-sample jump at the wrap
    p99.9/99.99 : interior |first-difference| percentiles (the natural scale)
    xf20/xf50: max delta inside + at both edges of a 20/50 ms wrap-around
               crossfade that blends the last N samples with the first N
    """
    x = read_pcm_f32(path)
    d = np.abs(np.diff(x, axis=0))
    p999 = float(np.percentile(d, 99.9))
    p9999 = float(np.percentile(d, 99.99))
    jstep = float(np.max(np.abs(x[0] - x[-1])))
    out = {'step': jstep, 'p99.9': p999, 'p99.99': p9999}
    for ms in (20, 50):
        M = int(round(ms * SR / 1000))
        tail, head = x[-M:], x[:M]
        w = np.linspace(0.0, 1.0, M)[:, None]
        blend = tail * (1.0 - w) + head * w
        bd = np.abs(np.diff(blend, axis=0))
        edge1 = float(np.max(np.abs(blend[0] - x[-M - 1])))
        edge2 = float(np.max(np.abs(x[M] - blend[-1])))
        out[f'xf{ms}'] = float(max(bd.max(), edge1, edge2))
        out[f'gap{ms}'] = float(np.max(np.abs(tail - head)))
    return out


def main():
    rows, fails, loopres = [], [], {}
    files = ([(p, 'sfx') for p in sorted(glob.glob(os.path.join(ROOT, 'sfx', '*.ogg')))] +
             [(p, 'music') for p in sorted(glob.glob(os.path.join(ROOT, 'music', '*.ogg')))])
    for path, kind in files:
        name = os.path.splitext(os.path.basename(path))[0]
        st = ffprobe(path)
        x = read_pcm_f32(path)
        ln = loudnorm_measure(path) or {'tp': peak_db(x), 'lufs': float('nan')}
        pk, r, dc = peak_db(x), rms_db(x), float(np.mean(x))
        tp, lufs = ln['tp'], ln['lufs']
        checks, notes = [], ''
        if kind == 'sfx':
            checks = [st['codec'] == 'vorbis', st['sr'] == 44100, st['ch'] == 1,
                      st['dur'] <= SFX_DUR.get(name, 1.20) + 1e-6,
                      pk <= SFX_PEAK_MAX, tp <= SFX_PEAK_MAX,
                      r > RMS_FLOOR, abs(dc) <= DC_MAX]
            mono = None
        else:
            m = read_mono(path)
            mpk, mrms = peak_db(m), rms_db(m)
            dmin, dmax = MUSIC_SPEC[name]
            lm = loop_metrics(path)
            loopres[name] = lm
            checks = [st['codec'] == 'vorbis', st['sr'] == 44100, st['ch'] == 2,
                      dmin - 0.5 <= st['dur'] <= dmax + 0.5,
                      tp <= MUSIC_TP_MAX, pk <= MUSIC_TP_MAX,
                      NATIVE_RMS[0] <= r <= NATIVE_RMS[1],
                      mpk <= MONO_PEAK_MAX, mrms <= MONO_RMS_MAX,
                      MONO_RMS_TGT[0] <= mrms <= MONO_RMS_TGT[1],
                      r > RMS_FLOOR, abs(dc) <= DC_MAX,
                      lm['step'] <= lm['p99.99']]
            notes = f'{mpk:.2f}/{mrms:.2f}'
            mono = (mpk, mrms)
        ok = all(checks)
        if not ok:
            fails.append(name)
        rows.append((f'{kind}/{name}.ogg', st['dur'], st['ch'], pk, tp, r, dc,
                     lufs, notes, 'PASS' if ok else 'FAIL'))

    print('| file | dur (s) | ch | peak dBFS | true peak dBTP | RMS dBFS | DC | LUFS |'
          ' mono peak/RMS | result |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for f, dur, ch, pk, tp, r, dc, lufs, notes, res in rows:
        ls = f'{lufs:.1f}' if lufs == lufs else 'n/a'
        print(f'| {f} | {dur:.3f} | {ch} | {pk:.2f} | {tp:.2f} | {r:.2f} | '
              f'{dc:+.5f} | {ls} | {notes} | {res} |')
    print()
    print('LOOP CONTINUITY (wrap-around discontinuity per music file)')
    print('| loop | wrap step | interior p99.9 | interior p99.99 | 20 ms xfade max delta |'
          ' 50 ms xfade max delta | head-vs-tail gap 20 ms | verdict |')
    print('|---|---|---|---|---|---|---|---|')
    for name, m in loopres.items():
        verdict = 'seamless' if m['step'] <= m['p99.99'] else 'CHECK'
        print(f"| {name}.ogg | {m['step']:.6f} | {m['p99.9']:.6f} | {m['p99.99']:.6f} | "
              f"{m['xf20']:.6f} | {m['xf50']:.6f} | {m['gap20']:.6f} | {verdict} |")
    print()
    rms_all = [r[5] for r in rows]
    STINGERS = {'level-up', 'alert', 'horn', 'roar', 'victory', 'defeat'}
    sfx_rms = [r[5] for r in rows
               if r[0].startswith('sfx/') and r[0].split('/')[1][:-4] not in STINGERS]
    print(f'pack RMS spread: {max(rms_all) - min(rms_all):.2f} dB '
          f'({min(rms_all):.2f} .. {max(rms_all):.2f}); '
          f'in-game SFX (stingers excluded): {max(sfx_rms) - min(sfx_rms):.2f} dB '
          f'({min(sfx_rms):.2f} .. {max(sfx_rms):.2f})')
    print('FAILED: ' + ', '.join(fails) if fails else 'ALL FILES PASS')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
