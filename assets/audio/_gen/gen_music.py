#!/usr/bin/env python3
"""EMBERFALL music loops (menu / battle / night). All parts synthesized from
scratch. Loop buffers are rendered with wrap-around event placement and
circular filtering/reverb, so every track is periodic by construction."""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from dsp import *

WAV = '/tmp/emberfall_wav'
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'music')
MCEIL = db(-6.6)          # native stereo ceiling; leaves room for codec TP
                          # overshoot so mono downmix peak stays under -1 dBFS
MRMS = -21.4              # native stereo bed level (music spec: <= -18 in mono QA)
MONO_RMS_TGT = -18.6      # what tools/qa/audio_review.py measures (ffmpeg -ac 1)
MONO_PEAK_MAX = -1.4      # QA gate is -1.0 on that mono downmix; keep margin
NATIVE_TP_MAX = -3.9      # native true peak (spec: <= -1 dBFS; keeps mono <= -1.4)


def pan2(v, pan):
    a = (pan + 1.0) * np.pi / 4
    return np.vstack([np.cos(a) * v, np.sin(a) * v])


def env_of(points, x):
    xs, ys = zip(*points)
    return float(np.interp(x, xs, ys))


# ================================================================= voices
def cello_note(f, d, attack=0.22, release=0.7, lvl=1.0, seed=0):
    """Bowed cello: band-limited saw + body resonances + bow noise."""
    n = ns(d)
    f0 = vib(f, n, 4.6, 0.0035, 0.35)
    y = saw_f0(f0, n, nharm=70, rolloff=1.2)
    y += 0.30 * np.sin(np.cumsum(TAU * f0 * 0.5) / SR)
    y = y / (peak(y) + 1e-9)
    bn = filt(noise(n, seed + 3), 'bp', (min(f * 2.5, 3000), min(f * 9 + 2500, 9500)), 2)
    y = y + 0.10 * bn
    y = resonators(y, [215, 455, 900], [4, 3, -2], q=2.2)
    y = filt(y, 'lp', 4500, 2)
    e = env_swell(n, attack, release, 1.0)
    e *= (1.0 + 0.05 * np.sin(TAU * 0.9 * tt(n) + seed))
    return y * e * lvl


def choir_note(f, d, attack, release, lvl, seed, formants=(700, 1150, 2600),
               gains=(8, 5, -4), rolloff=1.35, lp=4200):
    """Choir voice: detuned saw stack through vowel formants + breath."""
    n = ns(d)
    rng = np.random.default_rng(seed)
    y = np.zeros(n)
    for c in (-7.0, 0.0, 6.0):
        y += saw_f0(np.full(n, f * 2 ** (c / 1200.0)), n, nharm=45,
                    rolloff=rolloff, ph0=float(rng.uniform(0, 6)))
    y += 0.55 * saw_f0(np.full(n, f * 0.5 * 2 ** (rng.uniform(-4, 4) / 1200.0)),
                       n, nharm=35, rolloff=1.5)
    y = y / (peak(y) + 1e-9)
    y = y + 0.07 * filt(noise(n, seed + 11), 'bp', (600, 3500), 2)
    y = resonators(y, list(formants), list(gains), q=3.2)
    y = filt(y, 'lp', lp, 2)
    e = env_swell(n, attack, release, 1.0)
    e *= (1.0 + 0.06 * np.sin(TAU * 0.13 * tt(n) + seed))
    return y * e * lvl


def pad_st(notes, d, attack, release, fc, lvl, seed=0, spread=0.7, oct_up=False):
    """Stereo string pad: each voice panned across the field (cold, still)."""
    m = ns(d)
    out = np.zeros((2, m))
    L = max(len(notes) - 1, 1)
    for i, f in enumerate(notes):
        rng = np.random.default_rng(seed * 97 + i)
        v = np.zeros(m)
        for c in (-5.0, 5.0):
            v += saw(f * 2 ** (c / 1200.0), m,
                     ph=float(rng.uniform(0, 6)), rolloff=1.35)
        v *= (1.0 + 0.004 * np.sin(TAU * 0.07 * tt(m) + i))
        if oct_up:
            v += 0.45 * saw(f * 2 * 2 ** (rng.uniform(-4, 4) / 1200.0), m,
                            ph=float(rng.uniform(0, 6)), rolloff=1.5)
        out += pan2(v, -spread + 2 * spread * i / L)
    out = filt(out, 'lp', fc, 2)
    out *= env_swell(m, attack, release, 1.0)[None, :]
    return out * (lvl / len(notes))


def solo_string(f, d, lvl, attack=0.10, release=0.4, pan=-0.12, seed=0, harm=90):
    """Melody voice: brighter, focused violin/low-string line."""
    n = ns(d)
    f0 = vib(f, n, 5.2, 0.0045, 0.22)
    y = saw_f0(f0, n, nharm=harm, rolloff=1.05)
    y = y / (peak(y) + 1e-9)
    y += 0.07 * filt(noise(n, seed + 5), 'bp', (f * 2, min(f * 7 + 2000, 9000)), 2)
    y = resonators(y, [400, 1400], [3, -2], q=1.8)
    y = filt(y, 'lp', 7000, 2)
    e = env_swell(n, attack, release, 1.0)
    e *= (1.0 + 0.04 * np.sin(TAU * 4.7 * tt(n) + seed) * np.clip(tt(n) / 0.4, 0, 1))
    return pan2(y * e * lvl, pan)


def bass_note(f, d, lvl, attack=0.12, release=0.5):
    """Low string/bass drone root (centre)."""
    n = ns(d)
    y = np.sin(TAU * f * tt(n)) + 0.35 * np.sin(TAU * 2 * f * tt(n))
    y += 0.20 * saw(f, n, rolloff=1.7)
    y = filt(y, 'lp', 320, 2)
    return pan2(y * env_swell(n, attack, release, 1.0) * lvl, 0.0)


def bone_hit(big=True, lvl=1.0, seed=0):
    """Deep bone/tom hit for the marching pulse."""
    d = 0.45 if big else 0.30
    n = ns(d)
    if big:
        sw, body, tau, click_bp = (78, 46), [155, 260], 0.17, (450, 2200)
    else:
        sw, body, tau, click_bp = (112, 74), [215, 355], 0.09, (700, 3200)
    y = sine_sweep(sw[0], sw[1], n) * env_exp(n, tau, 0.0015)
    y += 0.55 * modal(body, [1.0, 0.5], [tau * 0.55, tau * 0.35], n, seed=seed)
    y += 0.40 * filt(noise(n, seed + 1), 'bp', click_bp, 2) * env_exp(n, 0.006, 0.0005)
    y += 0.30 * filt(noise(n, seed + 2), 'bp', (140, 620), 2) * env_exp(n, 0.03, 0.002)
    return y * lvl


def bone_clack(lvl=1.0, seed=0):
    """Dry bone rattle on the off-beats."""
    n = ns(0.09)
    y = modal([1150, 2300, 3400], [1.0, 0.5, 0.3], [0.030, 0.020, 0.014], n, seed=seed)
    y += 0.5 * filt(noise(n, seed + 1), 'bp', (1000, 5000), 2) * env_exp(n, 0.004, 0.0006)
    return y * lvl


def hah(f, lvl, seed, dur=0.17):
    """Short male-choir 'hah' stab (marching spine)."""
    n = ns(dur)
    y = saw_f0(np.full(n, f), n, nharm=40, rolloff=1.2)
    y += 0.6 * saw_f0(np.full(n, f * 2), n, nharm=30, rolloff=1.45)
    y = y / (peak(y) + 1e-9)
    y = y + 0.22 * filt(noise(n, seed), 'bp', (900, 4000), 2)
    y = resonators(y, [700, 1150, 2500], [9, 5, -4], q=3.0)
    y = filt(y, 'lp', 4500, 2)
    return y * env_adsr(n, 0.018, 0.05, 0.55, 0.07) * lvl


# ================================================================= MENU (72 s)
MENU_T = 72.0
MENU_BAR = 4.0                      # 60 BPM, 4/4 -> 18 bars


def build_menu():
    L = LoopBuf(MENU_T, 2)
    # --- ash bed: two decorrelated pink layers, LP'd, slowly breathing -------
    for c, seed in enumerate((401, 402)):
        w = pink(L.n, seed)
        w = fft_filt(w, 'lp', 1200, 2)
        t_ = L.t
        amp = 0.62 + 0.22 * np.sin(TAU * 5 * t_ / MENU_T + c) + \
              0.16 * np.sin(TAU * 7 * t_ / MENU_T + 1.1 + c * 2)
        L.buf[c] += w * np.clip(amp, 0.15, None) * 0.085
        rum = fft_filt(pink(L.n, seed + 50), 'lp', 150, 2)
        L.buf[c] += rum * 0.05
    # --- ember crackle: sparse bright pops, panned randomly -----------------
    rng = np.random.default_rng(9001)
    t = -float(rng.uniform(0.0, 0.25))
    while True:
        t += float(rng.uniform(0.05, 0.42))
        if t >= MENU_T:
            break
        m = ns(float(rng.uniform(0.004, 0.020)))
        if rng.random() < 0.75:
            lo, hi = 1500.0, 5000.0
        else:
            lo, hi = 700.0, 2400.0
        b = filt(noise(m, int(rng.integers(1, 1 << 30))), 'bp', (lo, hi), 2)
        b *= env_exp(m, 0.004, 0.0004)
        L.add(t, b * float(rng.uniform(0.15, 1.0)) * 0.10,
              pan=float(rng.uniform(-0.85, 0.85)))
    # --- solo cello phrases (long silences between them) --------------------
    phrases = [
        (0.0, 1.8, 146.83, 1.00), (2.4, 1.4, 174.61, 0.92), (4.8, 2.2, 164.81, 0.85),
        (12.0, 1.6, 220.00, 0.95), (14.0, 1.2, 196.00, 0.90), (15.6, 2.4, 174.61, 0.98),
        (26.0, 3.4, 73.42, 0.85), (30.5, 2.8, 110.00, 0.80),
        (34.0, 3.2, 87.31, 0.82), (38.0, 4.0, 82.41, 0.78),
        (52.0, 1.6, 174.61, 0.95), (54.2, 1.4, 164.81, 0.90), (56.2, 3.0, 146.83, 0.85),
        (66.0, 6.0, 73.42, 0.72),
    ]
    for i, (t0, d, f, lvl) in enumerate(phrases):
        sig = cello_note(f, d, attack=0.24 if d > 2 else 0.16, release=min(0.8, d * 0.45),
                         lvl=lvl, seed=i * 13)
        L.add(t0, sig, pan=-0.30)
    # --- the one warm choir chord: Dm add9, never resolved ------------------
    sig = np.zeros((2, ns(26.0)))
    for j, f in enumerate([73.42, 146.83, 174.61, 220.00, 329.63]):
        v = choir_note(f, 26.0, attack=4.0, release=7.0, lvl=[0.9, 1.0, 0.85, 0.7, 0.45][j],
                       seed=611 + j, formants=(620, 1050, 2450), gains=(7, 6, -4))
        sig += pan2(v, -0.55 + 1.1 * j / 4)
    L.add(24.0, sig * 0.75)
    # --- mix ---------------------------------------------------------------
    mix = L.buf
    mix = mix - np.mean(mix, axis=1, keepdims=True)
    ir = make_ir(2.0, 0.65, 5000, 150, 0.03, 405)
    mix = circ_rev(mix, ir, wet=0.20)
    return mix


# ================================================================= BATTLE (114.29 s)
BEAT = 31500                      # samples @ 84 BPM (exact)
BAR = 4 * BEAT
BARS = 40
BATTLE_T = BARS * BAR / SR        # 114.2857 s

# (name, stab root Hz, string voicing, bass root Hz)
CHORDS = [
    ('Dm', 73.42,  [293.66, 349.23, 440.00], 73.42),
    ('Dm', 73.42,  [293.66, 349.23, 440.00], 73.42),
    ('Bb', 116.54, [233.08, 293.66, 349.23], 58.27),
    ('F',  87.31,  [261.63, 349.23, 440.00], 87.31),
    ('Gm', 98.00,  [196.00, 233.08, 293.66], 98.00),
    ('Gm', 98.00,  [196.00, 233.08, 293.66], 98.00),
    ('Bb', 116.54, [233.08, 293.66, 349.23], 58.27),
    ('A',  110.00, [220.00, 277.18, 329.63], 55.00),
]

MEL = {
    16: [(0.0, 2.0, 440.00), (2.0, 1.0, 392.00), (3.0, 1.0, 349.23)],
    17: [(0.0, 2.0, 329.63), (2.0, 2.0, 293.66)],
    18: [(0.0, 2.0, 349.23), (2.0, 1.5, 392.00), (3.5, 0.5, 440.00)],
    19: [(0.0, 4.0, 440.00)],
    20: [(0.0, 2.0, 392.00), (2.0, 2.0, 349.23)],
    21: [(0.0, 4.0, 293.66)],
    22: [(0.0, 2.0, 349.23), (2.0, 2.0, 293.66)],
    23: [(0.0, 2.0, 277.18), (2.0, 2.0, 329.63)],
}


def tbar(b, beat=0.0):
    return (b * BAR + beat * BEAT) / SR


def build_battle():
    """Dead army marching — 84 BPM heartbeat pulse in D minor, built as a real
    arc that returns to its own starting level so the loop point is inaudible:
      bars 0-2   low choir bed only (drums out)
      bars 3-5   sparse half-time bone hits enter
      bars 6-15  full heartbeat + bone rattle, cold strings swell in
      bars 16-23 bass + 'hah' stabs join, melody enters at 20
      bars 24-33 full ensemble, octave strings on top
      bars 34-37 decrescendo
      bars 38-39 sparse again -> back into the intro bed at the loop point
    """
    L = LoopBuf(BATTLE_T, 2)
    perc_e = lambda b: env_of([(0, 0.0), (2, 0.0), (3, 0.45), (6, 0.62),
                               (12, 0.85), (16, 1.0), (33, 1.0), (37, 0.70),
                               (38, 0.45), (39, 0.38), (40, 0.0)], b)
    clack_e = lambda b: env_of([(0, 0.0), (6, 0.55), (12, 0.85), (16, 1.0),
                                (34, 1.0), (37, 0.5), (38, 0.0), (40, 0.0)], b)
    stab_e = lambda b: env_of([(0, 0.0), (12, 0.6), (16, 0.9), (24, 1.0),
                               (33, 1.0), (36, 0.6), (37.5, 0.0), (40, 0.0)], b)
    str_e = lambda b: env_of([(0, 0.20), (4, 0.30), (8, 0.45), (16, 0.70),
                              (24, 0.90), (32, 1.00), (36, 0.90), (39, 0.40),
                              (40, 0.20)], b)
    mel_e = lambda b: env_of([(0, 0.0), (20, 0.6), (24, 0.9), (32, 1.0),
                              (35, 0.8), (37, 0.3), (37.5, 0.0), (40, 0.0)], b)
    bas_e = lambda b: env_of([(0, 0.0), (8, 0.5), (16, 0.8), (24, 1.0),
                              (34, 1.0), (38, 0.5), (40, 0.0)], b)
    drn_e = lambda b: env_of([(0, 0.50), (4, 0.60), (16, 0.80), (24, 1.00),
                              (34, 1.00), (38, 0.70), (40, 0.50)], b)

    for b in range(BARS):
        _, root, voice, bassf = CHORDS[b % 8]
        pe, cl, se, s2, me, be, de = (perc_e(b), clack_e(b), stab_e(b),
                                      str_e(b), mel_e(b), bas_e(b), drn_e(b))
        sparse = (b < 6) or (b >= 38)
        # ---- marching spine: heartbeat pulse (accent / ghost) -------------
        if pe > 0.01:
            beats = (0.0, 2.0) if sparse else (0.0, 1.0, 2.0, 3.0)
            for beat in beats:
                big = beat in (0.0, 2.0)
                L.add(tbar(b, beat),
                      bone_hit(big, (1.0 if big else 0.55) * pe,
                               seed=b * 17 + int(beat)))
        if cl > 0.01:                                   # bone rattle on the "&"
            for k, beat in enumerate((0.5, 1.5, 2.5, 3.5)):
                L.add(tbar(b, beat),
                      bone_clack(0.16 * cl * (1.0 if beat in (1.5, 3.5) else 0.7),
                                 seed=b * 31 + k))
        # ---- male choir 'hah' stabs --------------------------------------
        if se > 0.01:
            for j, (beat, lvl) in enumerate([(0.0, 0.95), (1.5, 0.55),
                                             (2.0, 0.75), (3.5, 0.50)]):
                s = hah(root, lvl * se, seed=b * 71 + j)
                L.add(tbar(b, beat), pan2(s, 0.22 if j % 2 else -0.22))
                L.add(tbar(b, beat), pan2(hah(root * 2, 0.30 * lvl * se,
                                              seed=b * 71 + j + 7), 0.0))
        # ---- low male choir drone / intro bed (every 2 bars) -------------
        if b % 2 == 0 and de > 0.01:
            d = 2 * BAR / SR + 1.2
            L.add(tbar(b, 0), pan2(
                choir_note(root, d, attack=1.1, release=1.4, lvl=de * 0.9,
                           seed=811 + b, formants=(560, 950, 2300),
                           gains=(7, 5, -5), rolloff=1.5, lp=3200), 0.0))
        # ---- cold string swells ------------------------------------------
        if s2 > 0.01:
            L.add(tbar(b, 0), pad_st(voice, BAR / SR + 1.0, attack=0.85,
                                     release=1.3, fc=3600, lvl=s2 * 0.55,
                                     seed=b))
            if b >= 24:
                L.add(tbar(b, 0), pad_st(voice, BAR / SR + 1.0, attack=1.1,
                                         release=1.3, fc=6500, lvl=s2 * 0.22,
                                         seed=b + 400, oct_up=True))
        # ---- bass root ----------------------------------------------------
        if be > 0.01:
            L.add(tbar(b, 0), bass_note(bassf, BAR / SR + 0.35, lvl=be * 0.55))
        # ---- melody (enters bar 20, octave up from bar 24) ----------------
        if me > 0.01 and b < 38:
            key = b if b < 24 else (b - 16 if b >= 32 else b - 8)
            for j, (beat, dl, f) in enumerate(MEL.get(key, [])):
                if b >= 24:
                    f = f * 2                   # second pass an octave up (cold)
                L.add(tbar(b, beat),
                      solo_string(f, dl * BEAT / SR + 0.45, lvl=me * 0.45,
                                  attack=0.12, release=0.5, pan=-0.18 + 0.06 * j,
                                  seed=b * 13 + j))
    mix = L.buf
    mix = mix - np.mean(mix, axis=1, keepdims=True)
    ir = make_ir(1.4, 0.45, 6000, 120, 0.02, 805)
    mix = circ_rev(mix, ir, wet=0.17)
    return mix


# ================================================================= NIGHT (72 s)
NIGHT_T = 72.0


def cricket(dur, f, rate, lvl, seed):
    n = ns(dur)
    t_ = tt(n)
    pulse = np.sin(TAU * rate * t_) ** 8
    car = np.sin(TAU * f * t_ + 0.3 * np.sin(TAU * 6 * t_))
    y = car * pulse * env_swell(n, 0.05, 0.30, 1.0)
    y = filt(y, 'bp', (f * 0.82, min(f * 1.2, 15000)), 2)
    return y * lvl


def build_night():
    bed = LoopBuf(NIGHT_T, 2)
    ev = LoopBuf(NIGHT_T, 2)
    T = NIGHT_T
    t_ = bed.t
    # --- wind: two decorrelated layers, periodic LFOs (integer cycles) ------
    for c, seed in enumerate((501, 502)):
        w = fft_filt(pink(bed.n, seed), 'lp', 900, 2)
        amp = (0.50 + 0.30 * np.sin(TAU * 4 * t_ / T + 1.7 * c)
                    + 0.22 * np.sin(TAU * 7 * t_ / T + 0.6 + 2.1 * c)
                    + 0.16 * np.sin(TAU * 5 * t_ / T + 2.9 + c))
        bed.buf[c] += w * np.clip(amp, 0.18, None) * 0.34
        # air hiss layer: smooth band around 2.6 kHz (circular -> loop-safe)
        h = np.fft.rfft(pink(bed.n, seed + 77))
        frq = np.fft.rfftfreq(bed.n, 1.0 / SR)
        mask = np.exp(-((np.log2(np.maximum(frq, 1.0) / 2600.0)) ** 2) / 1.1)
        h = h * mask
        hs = np.fft.irfft(h, n=bed.n)
        hs = hs / (np.max(np.abs(hs)) + 1e-9)
        amp2 = 0.55 + 0.35 * np.sin(TAU * 6 * t_ / T + 1.3 + 1.9 * c)
        bed.buf[c] += hs * np.clip(amp2, 0.15, None) * 0.10
    # --- distant water: slow-breathing mid noise, slightly right ------------
    for c, seed in enumerate((521, 522)):
        w = np.fft.rfft(pink(bed.n, seed))
        frq = np.fft.rfftfreq(bed.n, 1.0 / SR)
        mask = np.exp(-((np.log2(np.maximum(frq, 1.0) / 1100.0)) ** 2) / 1.4)
        wa = np.fft.irfft(w * mask, n=bed.n)
        wa = wa / (np.max(np.abs(wa)) + 1e-9)
        amp = (0.45 + 0.30 * np.sin(TAU * 3 * t_ / T + 0.9 + 1.5 * c)
                    + 0.25 * np.sin(TAU * 5 * t_ / T + 2.2 + c))
        bed.buf[c] += wa * np.clip(amp, 0.15, None) * (0.13 if c == 0 else 0.17)
    # --- sparse crickets ----------------------------------------------------
    rng = np.random.default_rng(531)
    times = [3.2, 9.5, 17.0, 26.4, 33.1, 47.6, 55.0, 61.3, 68.9]
    for i, t0 in enumerate(times):
        f = float(rng.uniform(4300, 5400))
        ev.add(t0, cricket(float(rng.uniform(0.35, 0.65)), f,
                           float(rng.uniform(21, 29)),
                           float(rng.uniform(0.5, 1.0)) * 0.13, seed=540 + i),
               pan=float(rng.uniform(-0.8, 0.8)))
    # --- one far-off bell ---------------------------------------------------
    n = ns(6.0)
    bell = modal([196.0, 392.0, 586.0, 784.0, 1078.0, 1420.0],
                 [1.0, 0.60, 0.40, 0.28, 0.18, 0.12],
                 [3.2, 2.2, 1.6, 1.1, 0.8, 0.6], n, seed=551)
    bell = filt(bell, 'lp', 1700, 2)
    ev.add(41.0, pan2(bell * 0.24, -0.25))
    # --- space --------------------------------------------------------------
    evm = ev.buf - np.mean(ev.buf, axis=1, keepdims=True)
    ir = make_ir(3.2, 0.9, 3500, 150, 0.05, 561)
    evm = circ_rev(evm, ir, wet=0.50)
    mix = bed.buf + evm
    mix = mix - np.mean(mix, axis=1, keepdims=True)
    return mix


# ================================================================= render
BUILDERS = {'menu': (build_menu, (60.0, 90.0)),
            'battle': (build_battle, (90.0, 120.0)),
            'night': (build_night, (60.0, 90.0))}


def encode(wav_path, ogg_path, q=6):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav_path,
                    '-c:a', 'libvorbis', '-q:a', str(q), ogg_path], check=True)


def read_mono(path):
    """Mono downmix exactly like tools/qa/audio_review.py (ffmpeg -ac 1)."""
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1',
                        '-f', 'f32le', '-'], capture_output=True)
    return np.frombuffer(r.stdout, dtype='<f4')


def measure(path):
    x = read_pcm_f32(path)
    ln = loudnorm_measure(path) or {'tp': peak_db(x), 'lufs': float('nan')}
    m = read_mono(path)
    return dict(pk=peak_db(x), tp=ln['tp'], rms=rms_db(x),
                mpk=peak_db(m), mrms=rms_db(m), lufs=ln['lufs'])


def render(name):
    fn, (dmin, dmax) = BUILDERS[name]
    mix = fn()
    assert mix.shape[0] == 2 and np.max(np.abs(mix)) > 1e-6
    # gain search runs through limiter + circular 20 Hz high-pass, so the
    # shipped file is DC-free, loop-safe and lands on the target bed level
    y = balance_chain(mix, MRMS, MCEIL, g_hi=2.5, hp=20, circular=True)
    wav = os.path.join(WAV, name + '.wav')
    ogg = os.path.join(OUT, name + '.ogg')
    m = {}
    for _ in range(6):
        write_wav(wav, y)
        encode(wav, ogg)
        m = measure(ogg)
        head = min(MONO_PEAK_MAX - m['mpk'], NATIVE_TP_MAX - m['tp'])
        if head < 0.0:                      # over a peak ceiling -> scale down
            y = y * db(head)
            continue
        err = m['mrms'] - MONO_RMS_TGT
        if err > 0.15 or (err < -0.15 and -err <= head):
            y = y * db(-err)                # trim bed level within peak headroom
            continue
        break
    st = ffprobe(ogg)
    print(f"{name:8s} dur={st['dur']:.3f}s ch={st['ch']} native: peak={m['pk']:6.2f} "
          f"tp={m['tp']:6.2f} rms={m['rms']:6.2f} | mono(-ac 1): peak={m['mpk']:6.2f} "
          f"rms={m['mrms']:6.2f} lufs={m['lufs']:6.2f} | spec={dmin}-{dmax}s")
    ok = (st['dur'] >= dmin - 0.5 and st['dur'] <= dmax + 0.5
          and m['mpk'] <= -1.0 and m['tp'] <= -1.0
          and m['mrms'] <= -18.0 and -19.2 <= m['mrms']     # QA gate + target window
          and m['rms'] <= -18.0 and m['pk'] <= -1.0)        # native contract ceilings
    return ok


if __name__ == '__main__':
    os.makedirs(WAV, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    names = sys.argv[1:] or list(BUILDERS)
    bad = [n for n in names if not render(n)]
    print('ALL PASS' if not bad else 'FAILED: ' + ', '.join(bad))
    sys.exit(1 if bad else 0)
