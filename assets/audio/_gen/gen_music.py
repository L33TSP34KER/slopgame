#!/usr/bin/env python3
"""EMBERFALL music loops (menu / battle / night) — epic orchestral war-march.

Style targets (human directive): "make world of warcraft like music / dota 2
like / classical music but march of war".

  battle  120 BPM 4/4, D minor, 56 bars (112 s)
          intro -> theme A (horn) -> theme A (full) -> B lift -> break/build
          -> full reprise -> coda that decays into the intro level
  menu    66.7 BPM 4/4, D minor, 20 bars (72 s)
          solemn horn anthem over string pads, low choir, timpani heartbeat
  night   72 s quiet vale ambience + a very distant lone horn call and
          far-off low drum pulses mixed far under the bed

All parts synthesized from scratch. Loop buffers are rendered with
wrap-around event placement and circular filtering/reverb, so every track is
periodic by construction (reverb/delay tails wrap into the head).
"""
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
# night is the widest (most diffuse) mix, so its mono downmix sits closest to the
# native level; aim it a touch lower to keep verify.py's native RMS cap in reach
MONO_TGT = {'menu': -18.6, 'battle': -18.6, 'night': -18.78}
MONO_PEAK_MAX = -1.4      # QA gate is -1.0 on that mono downmix; keep margin
NATIVE_TP_MAX = -3.9      # native true peak (spec: <= -1 dBFS; keeps mono <= -1.4)
NATIVE_RMS_MAX = -19.0    # verify.py NATIVE_RMS ceiling on the shipped file


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


def choir_stab(f, lvl, seed, attack=0.045, release=0.30, dur=0.55,
               formants=(720, 1180, 2650), gains=(9, 6, -4), lp=4600):
    """Hard-attack short choir stab (march accents / cadences)."""
    return choir_note(f, dur, attack=attack, release=release, lvl=lvl, seed=seed,
                      formants=formants, gains=gains, rolloff=1.25, lp=lp)


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


def spiccato(f, d, lvl, seed=0, pan=-0.30, bright=1.0):
    """Short-attack staccato bowed note — the march string ostinato engine."""
    n = ns(d)
    y = saw_f0(np.full(n, f), n, nharm=55, rolloff=1.05 + 0.25 * (1.0 - bright))
    y += 0.55 * saw_f0(np.full(n, f * 2 ** (4.0 / 1200.0)), n, nharm=45,
                       rolloff=1.25, ph0=1.7)
    y += 0.35 * np.sin(TAU * f * 0.5 * tt(n))          # body weight
    y = y / (peak(y) + 1e-9)
    y += 0.08 * filt(noise(n, seed + 7), 'bp',
                     (min(f * 3, 2500), min(f * 8 + 2000, 7000)), 2)
    y = resonators(y, [420, 1050, 2500], [4, 3, 2], q=2.2)
    y = filt(y, 'lp', 4600 * bright, 2)
    e = env_adsr(n, 0.010, 0.12, 0.38, min(0.07, d * 0.4))
    return pan2(y * e * lvl, pan)


def bass_note(f, d, lvl, attack=0.12, release=0.5):
    """Low string/bass drone root (centre)."""
    n = ns(d)
    y = np.sin(TAU * f * tt(n)) + 0.35 * np.sin(TAU * 2 * f * tt(n))
    y += 0.20 * saw(f, n, rolloff=1.7)
    y = filt(y, 'lp', 320, 2)
    return pan2(y * env_swell(n, attack, release, 1.0) * lvl, 0.0)


def brass(f, d, lvl, attack=0.10, release=0.35, seed=0, bright=1.0,
          lp=4600, pan=0.0, oct_down=0.0, vib_depth=0.0035):
    """Section brass (horns / low brass): detuned saw stack through horn
    formants, swelling attack, delayed controlled vibrato, gentle saturation."""
    n = ns(d)
    rng = np.random.default_rng(seed + 17)
    y = np.zeros(n)
    for c in (-7.0, 0.0, 6.5):
        f0 = vib(f * 2 ** (c / 1200.0), n, 5.0, vib_depth, attack * 1.4 + 0.08)
        y += saw_f0(f0, n, nharm=60, rolloff=1.15, ph0=float(rng.uniform(0, 6)))
    if oct_down:
        y += oct_down * saw_f0(vib(f * 0.5, n, 5.0, vib_depth, attack * 1.4),
                               n, nharm=40, rolloff=1.45)
    y = y / (peak(y) + 1e-9)
    # horn formants: 300 Hz body, 800 Hz warmth, 1.6 kHz + presence bite
    y = resonators(y, [300, 800, 1600, 2900], [3, 3.5, 1.5 + 3.0 * bright, -3], q=1.5)
    y = filt(y, 'lp', lp, 2)
    y = y + 0.05 * filt(noise(n, seed + 3), 'bp', (900, 3000), 2) * \
        env_swell(n, attack * 0.5, min(release, 0.3), 1.0)
    y = y * env_swell(n, attack, release, 1.0)
    y = soft_sat(y, drive=1.3)
    return pan2(y * lvl, pan)


def snare(dur=0.24, lvl=1.0, seed=0, tight=1.0):
    """Filtered noise burst + shell modes + wire rattle, tight envelope."""
    n = ns(dur)
    y = filt(noise(n, seed), 'bp', (300, 7000), 2) * env_exp(n, 0.060 * tight, 0.0010)
    y += 0.55 * modal([185, 331, 487], [1.0, 0.55, 0.30],
                      [0.055 * tight, 0.038, 0.026], n, seed=seed + 1)
    y += 0.40 * filt(noise(n, seed + 2), 'bp', (2400, 7500), 2) * \
        env_exp(n, 0.032 * tight, 0.0007)
    y += 0.20 * filt(noise(n, seed + 3), 'bp', (5200, 11000), 2) * \
        env_exp(n, 0.012, 0.0004)
    return soft_sat(y * lvl * 0.55, 1.4)


def taiko(lvl=1.0, seed=0, big=True):
    """Deep war-drum: pitched sine drop + membrane modes + skin noise + room."""
    d = 0.75 if big else 0.50
    n = ns(d)
    f0, f1 = (96, 58) if big else (132, 86)
    y = sine_sweep(f0, f1, n) * env_exp(n, 0.22 if big else 0.15, 0.0015)
    y += 0.50 * modal([147, 236, 398], [1.0, 0.50, 0.25],
                      [0.13, 0.085, 0.05], n, seed=seed)
    y += 0.35 * filt(noise(n, seed + 1), 'bp', (110, 950), 2) * env_exp(n, 0.045, 0.0010)
    y += 0.16 * filt(noise(n, seed + 2), 'bp', (900, 3600), 2) * env_exp(n, 0.013, 0.0006)
    return soft_sat(y * lvl * 0.75, 1.3)


def timpani(f, lvl=1.0, seed=0, dur=2.4):
    """Tuned kettledrum: fundamental sweep + membrane modes + mallet noise."""
    n = ns(dur)
    y = sine_sweep(f * 1.035, f, n) * env_exp(n, 0.95, 0.004)
    y += 0.55 * modal([f * 1.50, f * 1.98, f * 2.44], [0.5, 0.3, 0.17],
                      [0.50, 0.34, 0.21], n, seed=seed)
    y += 0.45 * modal([f, f * 1.5, f * 2.0], [1.0, 0.42, 0.20],
                      [1.25, 0.72, 0.45], n, seed=seed + 1)
    y += 0.22 * filt(noise(n, seed + 2), 'bp', (max(f * 2.0, 130), 2600), 2) * \
        env_exp(n, 0.035, 0.0020)
    return soft_sat(y * lvl * 0.7, 1.2)


def crash(lvl=1.0, seed=0, dur=1.9):
    """Suspended-cymbal / crash swell for section downbeats."""
    n = ns(dur)
    y = filt(noise(n, seed), 'hp', 3200, 2) * env_exp(n, 0.55, 0.006)
    y += 0.45 * filt(noise(n, seed + 1), 'bp', (5500, 13000), 2) * env_exp(n, 0.95, 0.012)
    y *= (1.0 + 0.25 * np.sin(TAU * 7.3 * tt(n)))
    y = filt(y, 'lp', 11000, 2)
    return y * lvl * 0.5


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


def toll(f, lvl, seed=0, dur=5.0):
    """Tubular-bell / great-bell strike: hum note + inharmonic partials."""
    n = ns(dur)
    ratios = [0.5, 1.0, 2.00, 2.98, 4.15, 5.42, 6.80]
    amps = [0.55, 1.0, 0.62, 0.40, 0.26, 0.16, 0.10]
    taus = [4.2, 3.4, 2.3, 1.5, 1.0, 0.7, 0.45]
    y = modal([f * r for r in ratios], amps, taus, n, seed=seed)
    y += 0.25 * filt(noise(n, seed + 1), 'bp', (f * 2, 4200), 2) * env_exp(n, 0.02, 0.001)
    y = filt(y, 'lp', 3600, 2)
    return y * lvl * 0.5


# ================================================================= harmony
# chord -> bass root, spiccato (root, fifth), pad voicing (D4-A4 region),
# low-brass triad (D3-C#4 region), choir stab root
CH = {
    'Dm': dict(bass=73.42,  ost=(146.83, 220.00), pad=[293.66, 349.23, 440.00],
               tri=[146.83, 174.61, 220.00], stab=73.42),
    'Bb': dict(bass=58.27,  ost=(116.54, 174.61), pad=[293.66, 349.23, 466.16],
               tri=[146.83, 174.61, 233.08], stab=116.54),
    'F':  dict(bass=87.31,  ost=(174.61, 261.63), pad=[261.63, 349.23, 440.00],
               tri=[130.81, 174.61, 220.00], stab=87.31),
    'C':  dict(bass=65.41,  ost=(130.81, 196.00), pad=[261.63, 329.63, 392.00],
               tri=[130.81, 164.81, 196.00], stab=65.41),
    'Gm': dict(bass=98.00,  ost=(196.00, 293.66), pad=[293.66, 392.00, 466.16],
               tri=[146.83, 196.00, 233.08], stab=98.00),
    'A':  dict(bass=55.00,  ost=(220.00, 329.63), pad=[329.63, 440.00, 554.37],
               tri=[164.81, 220.00, 277.18], stab=110.00),
}

# ================================================================= BATTLE (112 s)
BEAT = 22050                      # samples @ 120 BPM (exact)
BAR = 4 * BEAT
BARS = 56                         # 7 x 8-bar phrases = 112.0 s
BATTLE_T = BARS * BAR / SR

P_A = ['Dm', 'Bb', 'F', 'C', 'Dm', 'Bb', 'Gm', 'A']        # theme A harmony
P_B = ['Bb', 'F', 'C', 'Dm', 'Bb', 'F', 'Gm', 'A']          # B lift (F major tilt)
BC = ['Dm', 'Bb', 'Gm', 'A'] * 2                            # break vamp
INTRO8 = ['Dm', 'Dm', 'Bb', 'Bb', 'Dm', 'Dm', 'Gm', 'A']
CODA8 = ['Dm', 'Bb', 'F', 'C', 'Dm', 'Gm', 'A', 'Dm']
BATTLE_CH = INTRO8 + P_A + P_A + P_B + BC + P_A + CODA8     # 56 bars

# --- main theme (horns): stepwise, dotted march rhythm, D natural minor ------
# (beat, dur_beats, Hz) per bar
THEME_A = [
    [(0.0, 1.5, 440.00), (1.5, 0.5, 466.16), (2.0, 1.0, 440.00), (3.0, 1.0, 392.00)],
    [(0.0, 1.5, 349.23), (1.5, 0.5, 392.00), (2.0, 1.0, 349.23), (3.0, 1.0, 293.66)],
    [(0.0, 1.5, 440.00), (1.5, 0.5, 466.16), (2.0, 1.0, 440.00), (3.0, 1.0, 392.00)],
    [(0.0, 1.5, 392.00), (1.5, 0.5, 440.00), (2.0, 1.0, 392.00), (3.0, 1.0, 329.63)],
    [(0.0, 1.5, 440.00), (1.5, 0.5, 466.16), (2.0, 1.0, 523.25), (3.0, 1.0, 587.33)],
    [(0.0, 2.0, 587.33), (2.0, 1.0, 523.25), (3.0, 1.0, 466.16)],
    [(0.0, 1.5, 392.00), (1.5, 0.5, 440.00), (2.0, 1.0, 466.16), (3.0, 1.0, 440.00)],
    [(0.0, 1.5, 440.00), (1.5, 0.5, 392.00), (2.0, 1.0, 349.23), (3.0, 1.0, 329.63)],
]
# --- B section: same stepwise shape lifted into the relative major -----------
THEME_B = [
    [(0.0, 1.5, 698.46), (1.5, 0.5, 783.99), (2.0, 1.0, 698.46), (3.0, 1.0, 587.33)],
    [(0.0, 1.5, 523.25), (1.5, 0.5, 587.33), (2.0, 1.0, 523.25), (3.0, 1.0, 440.00)],
    [(0.0, 1.5, 659.25), (1.5, 0.5, 698.46), (2.0, 1.0, 659.25), (3.0, 1.0, 783.99)],
    [(0.0, 2.0, 698.46), (2.0, 1.0, 659.25), (3.0, 1.0, 587.33)],
    [(0.0, 1.5, 587.33), (1.5, 0.5, 523.25), (2.0, 1.0, 466.16), (3.0, 1.0, 587.33)],
    [(0.0, 1.5, 523.25), (1.5, 0.5, 587.33), (2.0, 1.0, 523.25), (3.0, 1.0, 440.00)],
    [(0.0, 1.5, 466.16), (1.5, 0.5, 523.25), (2.0, 1.0, 587.33), (3.0, 1.0, 523.25)],
    [(0.0, 2.0, 659.25), (2.0, 2.0, 554.37)],
]
# --- coda: theme head, cadence, then air ------------------------------------
MEL_C = [
    [(0.0, 1.5, 440.00), (1.5, 0.5, 466.16), (2.0, 1.0, 440.00), (3.0, 1.0, 392.00)],
    [(0.0, 1.5, 349.23), (1.5, 0.5, 392.00), (2.0, 1.0, 349.23), (3.0, 1.0, 293.66)],
    [(0.0, 2.0, 440.00), (2.0, 1.0, 392.00), (3.0, 1.0, 349.23)],
    [(0.0, 4.0, 329.63)],
    [(0.0, 1.5, 349.23), (1.5, 0.5, 392.00), (2.0, 2.0, 440.00)],
    [(0.0, 4.0, 466.16)],
    [],
    [],
]

# per-layer dynamic envelopes over bar index (loop-closing values at 0/56)
OST_E = [(0, 0.45), (8, 0.62), (16, 0.85), (24, 0.95), (31, 0.95), (32, 0.74),
         (35, 0.78), (39, 1.00), (40, 1.15), (47, 1.15), (48, 1.00), (52, 0.72),
         (55, 0.45), (56, 0.45)]
BASS_E = [(0, 0.00), (4, 0.35), (8, 0.60), (16, 0.90), (24, 1.00), (32, 0.45),
          (36, 0.70), (40, 1.00), (48, 1.00), (52, 0.62), (54, 0.28), (55, 0.00),
          (56, 0.00)]
PAD_E = [(0, 0.35), (8, 0.50), (16, 0.70), (24, 0.90), (32, 0.58), (36, 0.75),
         (40, 1.00), (48, 0.95), (52, 0.70), (55, 0.42), (56, 0.35)]
DRN_E = [(0, 0.45), (8, 0.55), (16, 0.78), (24, 0.92), (32, 0.62), (36, 0.82),
         (40, 1.00), (48, 0.90), (52, 0.62), (55, 0.45), (56, 0.45)]
TIMP_E = [(0, 0.32), (8, 0.45), (16, 0.68), (24, 0.85), (32, 0.62), (38, 0.85),
          (40, 1.00), (48, 0.85), (52, 0.55), (55, 0.32), (56, 0.32)]
DRUM_E = [(0, 0.00), (5, 0.10), (7, 0.35), (8, 0.58), (15, 0.66), (16, 0.90),
          (23, 0.95), (24, 1.05), (31, 1.05), (32, 0.38), (35, 0.42), (36, 0.75),
          (39, 1.20), (40, 1.30), (47, 1.30), (48, 1.05), (50, 0.85), (52, 0.52),
          (54, 0.22), (55, 0.00), (56, 0.00)]
SNR_E = [(0, 0.00), (11, 0.00), (12, 0.45), (15, 0.50), (16, 0.85), (23, 0.90),
         (24, 1.00), (31, 1.00), (32, 0.00), (35, 0.00), (36, 0.55), (37, 0.65),
         (38, 1.00), (40, 1.15), (47, 1.15), (48, 1.00), (51, 0.85), (52, 0.45),
         (53, 0.00), (56, 0.00)]
STAB_E = [(0, 0.00), (15, 0.45), (16, 0.85), (24, 1.00), (31, 1.00), (32, 0.35),
          (36, 0.55), (39, 1.00), (40, 1.15), (47, 1.15), (48, 0.90), (51, 0.60),
          (53, 0.35), (54, 0.00), (56, 0.00)]
MEL_E = [(0, 0.00), (7, 0.30), (8, 0.58), (15, 0.62), (16, 0.85), (23, 0.90),
         (24, 1.00), (31, 1.00), (32, 0.00), (39, 0.00), (40, 1.15), (47, 1.15),
         (48, 1.00), (53, 0.70), (54, 0.00), (56, 0.00)]
BRS_E = [(0, 0.00), (8, 0.35), (16, 0.70), (24, 0.90), (31, 0.90), (32, 0.45),
         (36, 0.70), (39, 1.05), (40, 1.05), (47, 1.05), (48, 0.95), (52, 0.55),
         (54, 0.25), (55, 0.00), (56, 0.00)]

OST_PAT = [0, 0, 1, 0, 0, 1, 0, 1]        # 0 = chord root, 1 = fifth above
SNR_FULL = [(0.0, 1.0), (0.75, 0.35), (1.5, 0.70), (2.0, 0.90),
            (2.5, 0.30), (3.0, 0.70), (3.5, 0.55), (3.75, 0.45)]
SNR_LIGHT = [(0.0, 0.85), (1.5, 0.55), (2.0, 0.75), (3.0, 0.60), (3.5, 0.45)]
STAB_HITS = {16: [(0.0, 1.0), (2.0, 0.6)], 20: [(0.0, 0.7)],
             23: [(3.0, 0.7)], 24: [(0.0, 1.0), (2.0, 0.6)], 28: [(0.0, 0.7)],
             31: [(2.0, 0.7), (3.0, 0.9)], 35: [(3.0, 0.6)],
             39: [(2.0, 0.7), (3.0, 1.0)], 40: [(0.0, 1.0), (2.0, 0.7)],
             44: [(0.0, 0.8)], 47: [(2.0, 0.7), (3.0, 1.0)],
             48: [(0.0, 0.8)], 51: [(3.0, 0.6)], 53: [(0.0, 0.5)]}
SEC_STARTS = (8, 16, 24, 40, 48)
FILL_BARS = (7, 15, 23, 31, 39, 47)


def tbar(b, beat=0.0):
    return (b * BAR + beat * BEAT) / SR


def build_battle():
    """120 BPM D-minor war march. Form (56 bars):
      0-7   INTRO  — spiccato ostinato + timpani heartbeat, distant horn call
      8-15  THEME A — solo horns state the theme, taiko + light snare
      16-23 THEME A full — horns + strings doubled, choir stabs, march kit
      24-31 B LIFT — F-major tilt, high strings lead, low brass answers
      32-39 BREAK — vamp stripped to ostinato + taiko, snare roll crescendo
      40-47 REPRISE — tutti, loudest pass of the theme
      48-55 CODA — cadence, decrescendo back to the intro level for the loop
    """
    L = LoopBuf(BATTLE_T, 2)
    E = dict(ost=OST_E, bass=BASS_E, pad=PAD_E, drn=DRN_E, timp=TIMP_E,
             drum=DRUM_E, snr=SNR_E, stab=STAB_E, mel=MEL_E, brs=BRS_E)
    ev = {k: (lambda b, p=p: env_of(p, b)) for k, p in E.items()}

    for b in range(BARS):
        c = CH[BATTLE_CH[b]]
        oe, be, pe, de = ev['ost'](b), ev['bass'](b), ev['pad'](b), ev['drn'](b)
        te, ke, se, ste, me, bre = (ev['timp'](b), ev['drum'](b), ev['snr'](b),
                                    ev['stab'](b), ev['mel'](b), ev['brs'](b))
        # ---- march string ostinato: 8 spiccato eighths -------------------
        if oe > 0.01:
            for i, k in enumerate(OST_PAT):
                f = c['ost'][k]
                lvl = 0.34 * oe * (1.22 if i in (0, 4) else 0.9)
                L.add(tbar(b, i * 0.5), spiccato(f, 0.26, lvl,
                                                 seed=b * 41 + i, pan=-0.34))
                if b >= 16:                    # violin octave, wide right
                    L.add(tbar(b, i * 0.5), spiccato(f * 2, 0.26, 0.115 * oe,
                                                     seed=b * 41 + i + 900,
                                                     pan=0.34, bright=1.1))
        # ---- contrabass root ---------------------------------------------
        if be > 0.01:
            L.add(tbar(b, 0), bass_note(c['bass'], BAR / SR + 0.35,
                                        lvl=0.55 * be, attack=0.06, release=0.45))
        # ---- sustained string pad ----------------------------------------
        if pe > 0.01:
            L.add(tbar(b, 0), pad_st(c['pad'], BAR / SR + 1.1, attack=0.55,
                                     release=1.0, fc=4200, lvl=0.46 * pe, seed=b))
            if b >= 24 and b < 54:
                L.add(tbar(b, 0), pad_st(c['pad'], BAR / SR + 1.1, attack=0.75,
                                         release=1.0, fc=7000, lvl=0.16 * pe,
                                         seed=b + 500, oct_up=True))
        # ---- low male choir bed (every 2 bars) ---------------------------
        if b % 2 == 0 and de > 0.01:
            L.add(tbar(b, 0), pan2(choir_note(c['stab'], 2 * BAR / SR + 1.1,
                                               attack=1.0, release=1.4,
                                               lvl=0.34 * de, seed=811 + b,
                                               formants=(560, 950, 2300),
                                               gains=(7, 5, -5), rolloff=1.5,
                                               lp=3200), 0.0))
        # ---- timpani spine: downbeat + backbeat, section fills -----------
        if te > 0.01:
            L.add(tbar(b, 0), timpani(c['bass'], lvl=0.55 * te, seed=b * 13))
            if b >= 8:
                L.add(tbar(b, 2), timpani(c['bass'], lvl=0.30 * te, seed=b * 13 + 1))
            if b in FILL_BARS:
                for j, beat in enumerate((2.5, 3.0, 3.5)):
                    L.add(tbar(b, beat),
                          timpani(c['bass'], lvl=(0.18 + 0.16 * j) * te,
                                  seed=b * 13 + 5 + j, dur=1.2))
        # ---- taiko war drums ---------------------------------------------
        if ke > 0.01:
            if b < 16:
                beats = [(0.0, 1.0), (2.0, 0.62)]
            elif b < 32:
                beats = [(0.0, 1.0), (1.5, 0.50), (2.0, 0.72), (3.5, 0.55)]
            elif b < 38:
                beats = [(0.0, 1.0), (1.5, 0.55), (2.0, 0.72), (3.0, 0.50),
                         (3.5, 0.55)]
            else:
                beats = [(0.0, 1.0), (1.5, 0.55), (2.0, 0.72), (2.5, 0.50),
                         (3.0, 0.62), (3.5, 0.60)]
            for beat, lvl in beats:
                L.add(tbar(b, beat), taiko(lvl=lvl * ke * 0.55,
                                           seed=b * 29 + int(beat * 4),
                                           big=lvl > 0.7))
        # ---- snare: rudimental march figures ------------------------------
        if se > 0.01:
            if 38 <= b <= 39:                       # build roll (16ths, cresc)
                for i in range(16):
                    beat = i * 0.25
                    lvl = (0.22 + 0.75 * (i / 15.0)) * (1.35 if i % 4 == 0 else 1.0)
                    L.add(tbar(b, beat), snare(lvl=lvl * se * 0.5,
                                               seed=b * 61 + i, tight=1.0))
            elif b in (15, 23, 31, 47, 51):        # section-end 16th fill
                for i in range(8):
                    beat = 2.0 + i * 0.25
                    lvl = 0.35 + 0.60 * (i / 7.0)
                    L.add(tbar(b, beat), snare(lvl=lvl * se * 0.5,
                                               seed=b * 61 + i, tight=0.95))
            else:
                pat = SNR_FULL if (16 <= b < 32) or (b >= 40) or b == 48 else SNR_LIGHT
                for beat, lvl in pat:
                    L.add(tbar(b, beat), snare(lvl=lvl * se * 0.5,
                                               seed=b * 61 + int(beat * 4),
                                               tight=0.9 + 0.2 * (beat % 1.0)))
        # ---- choir stabs + mid choir wash ---------------------------------
        for beat, lvl in STAB_HITS.get(b, []):
            if ste > 0.01:
                s = hah(c['stab'], lvl * ste * 0.85, seed=b * 71 + int(beat))
                L.add(tbar(b, beat), pan2(s, 0.20))
                L.add(tbar(b, beat), pan2(hah(c['stab'] * 2, lvl * ste * 0.30,
                                               seed=b * 71 + int(beat) + 7), -0.10))
        if ste > 0.01 and b in (24, 26, 28, 30, 40, 42, 44, 46, 48, 50):
            for j, f in enumerate(c['pad']):
                L.add(tbar(b, 0), pan2(choir_note(f, 2 * BAR / SR + 1.0,
                                                   attack=0.45, release=1.1,
                                                   lvl=0.13 * ste, seed=907 + b * 5 + j,
                                                   formants=(760, 1200, 2700),
                                                   gains=(7, 5, -3), lp=5000),
                                       -0.4 + 0.4 * j))
        # ---- low brass harmony: dotted march stabs ------------------------
        if bre > 0.01:
            for j, f in enumerate(c['tri']):
                L.add(tbar(b, 0), brass(f, 1.55 * BEAT / SR, lvl=0.16 * bre,
                                        attack=0.05, release=0.22, seed=b * 7 + j,
                                        lp=3000, pan=-0.25 + 0.25 * j,
                                        bright=0.5, oct_down=0.35 if j == 0 else 0.0))
            L.add(tbar(b, 2), brass(c['tri'][0], 1.4 * BEAT / SR, lvl=0.12 * bre,
                                    attack=0.05, release=0.20, seed=b * 7 + 3,
                                    lp=2600, pan=0.0, bright=0.4, oct_down=0.35))
        # ---- cadence choir 'ah' (sustained accent on the phrase ends) -----
        if b in (15, 23, 31, 47) and ste > 0.01:
            for j, f in enumerate((c['tri'][1], c['tri'][2])):
                L.add(tbar(b, 3.0), pan2(choir_stab(f * 2, 0.16 * ste,
                                                     seed=b * 37 + j, dur=1.15,
                                                     attack=0.06, release=0.55),
                                         -0.25 + 0.5 * j))
        # ---- section crashes ------------------------------------------------
        if b in SEC_STARTS and ke > 0.01:
            L.add(tbar(b, 0), crash(lvl=0.24 * ke, seed=b * 5 + 1))
        # ---- the theme ----------------------------------------------------
        mel = None
        if 8 <= b < 32:
            mel = THEME_A[b - 8] if b < 16 else (THEME_A[b - 16] if b < 24
                                                 else THEME_B[b - 24])
        elif 40 <= b < 48:
            mel = THEME_A[b - 40]
        elif 48 <= b < 56:
            mel = MEL_C[b - 48]
        if mel and me > 0.01:
            for j, (beat, dl, f) in enumerate(mel):
                d = dl * BEAT / SR
                att = 0.075 if b < 24 else 0.055
                # horn line (the theme carrier)
                L.add(tbar(b, beat), brass(f, d + 0.30, lvl=0.52 * me,
                                           attack=att, release=0.30,
                                           seed=b * 19 + j, lp=4200,
                                           pan=0.06, bright=0.85,
                                           oct_down=0.22 if b < 16 else 0.30))
                if b >= 16:                     # strings double the horns
                    L.add(tbar(b, beat), solo_string(f, d + 0.35, lvl=0.30 * me,
                                                     attack=att, release=0.35,
                                                     pan=-0.22, seed=b * 19 + j + 3))
                    if b >= 24 and (b < 32 or b >= 40):
                        # octave sparkle on the B lift and the reprise
                        L.add(tbar(b, beat), solo_string(f * 2, d + 0.30,
                                                         lvl=0.13 * me, attack=att,
                                                         release=0.30, pan=0.30,
                                                         seed=b * 19 + j + 5))
                    if b >= 40:                 # choir doubles the reprise line
                        L.add(tbar(b, beat), pan2(choir_note(f, d + 0.45,
                                                              attack=0.14,
                                                              release=0.40,
                                                              lvl=0.10 * me,
                                                              seed=1301 + b * 3 + j,
                                                              lp=5200), 0.12))
        # ---- intro: distant horn foreshadow of the theme head --------------
        if b == 7:
            for j, (beat, dl, f) in enumerate(THEME_A[0]):
                L.add(tbar(b, beat), brass(f, dl * BEAT / SR + 0.5, lvl=0.20,
                                           attack=0.14, release=0.5, seed=700 + j,
                                           lp=2200, pan=0.18, bright=0.35,
                                           oct_down=0.4))
        # ---- break: rising dominant pedal + choir crescendo ----------------
        if b in (38, 39):
            for j, f in enumerate(CH['A']['tri']):
                L.add(tbar(b, 0), brass(f, BAR / SR + 0.5, lvl=0.20 * (0.8 if b == 38
                                                                      else 1.15),
                                        attack=1.4, release=0.5, seed=500 + j,
                                        lp=3400, pan=-0.2 + 0.2 * j, bright=0.5,
                                        oct_down=0.4))
            for j, f in enumerate([220.00, 277.18, 329.63, 440.00]):
                L.add(tbar(b, 0), pan2(choir_note(f, BAR / SR + 0.6,
                                                   attack=1.5 if b == 38 else 0.7,
                                                   release=0.4,
                                                   lvl=0.14 * (0.8 if b == 38 else 1.2),
                                                   seed=1401 + j,
                                                   formants=(720, 1180, 2650),
                                                   gains=(8, 5, -3), lp=5200),
                                       -0.45 + 0.3 * j))
    mix = L.buf
    mix = mix - np.mean(mix, axis=1, keepdims=True)
    ir = make_ir(1.5, 0.5, 6500, 130, 0.02, 805)
    mix = circ_rev(mix, ir, wet=0.20)
    return mix


# ================================================================= MENU (72 s)
MENU_T = 72.0
MENU_BEAT = 39690                  # samples @ 66.67 BPM (exact: 0.9 s)
MENU_BAR = 4 * MENU_BEAT           # 3.6 s
MENU_BARS = 20                     # 72.0 s

P_M = ['Dm', 'Bb', 'F', 'C', 'Dm', 'Bb', 'Gm', 'A']
MENU_CH = ['Dm', 'Dm', 'Gm', 'A'] + P_M + P_M

# horn anthem: solemn, stepwise, held notes (WoW capital-city main-menu feel)
MEL_M1 = [
    [(0.0, 3.0, 440.00), (3.0, 1.0, 466.16)],
    [(0.0, 2.0, 587.33), (2.0, 1.0, 523.25), (3.0, 1.0, 466.16)],
    [(0.0, 4.0, 440.00)],
    [(0.0, 3.0, 392.00), (3.0, 1.0, 329.63)],
    [(0.0, 2.0, 349.23), (2.0, 1.0, 392.00), (3.0, 1.0, 440.00)],
    [(0.0, 3.0, 466.16), (3.0, 1.0, 440.00)],
    [(0.0, 2.0, 392.00), (2.0, 1.0, 440.00), (3.0, 1.0, 466.16)],
    [(0.0, 4.0, 440.00)],
]
MEL_M2 = [
    [(0.0, 3.0, 440.00), (3.0, 1.0, 466.16)],
    [(0.0, 2.0, 587.33), (2.0, 1.0, 523.25), (3.0, 1.0, 466.16)],
    [(0.0, 4.0, 440.00)],
    [(0.0, 2.0, 392.00), (2.0, 2.0, 329.63)],
    [(0.0, 2.0, 349.23), (2.0, 1.0, 392.00), (3.0, 1.0, 440.00)],
    [(0.0, 2.0, 466.16), (2.0, 1.0, 440.00), (3.0, 1.0, 392.00)],
    [(0.0, 1.5, 440.00), (1.5, 0.5, 466.16), (2.0, 1.0, 440.00), (3.0, 1.0, 392.00)],
    [(0.0, 2.0, 349.23), (2.0, 2.0, 329.63)],
]

MENU_PAD_E = [(0, 0.38), (4, 0.66), (12, 0.95), (17, 0.95), (19, 0.58),
              (20, 0.38)]
MENU_HRN_E = [(0, 0.00), (4, 0.72), (11, 0.74), (12, 0.98), (17, 0.98),
              (19, 0.62), (20, 0.00)]
MENU_CHO_E = [(0, 0.34), (4, 0.60), (12, 0.86), (17, 0.80), (19, 0.55),
              (20, 0.34)]
MENU_TMP_E = [(0, 0.45), (8, 0.55), (12, 0.62), (18, 0.52), (20, 0.45)]


def tmen(b, beat=0.0):
    return (b * MENU_BAR + beat * MENU_BEAT) / SR


def build_menu():
    """Solemn, majestic, brooding — 66.67 BPM, D minor, 20 bars.
      0-3   INTRO  — ash bed, ember crackle, timpani heartbeat, distant horn
      4-11  ANTHEM — horn statement over string pads, low choir, cello answers
      12-19 ANTHEM'— fuller restatement, decays into the intro for the loop
    """
    L = LoopBuf(MENU_T, 2)
    # --- ash bed: two decorrelated pink layers, LP'd, slowly breathing -------
    for c, seed in enumerate((401, 402)):
        w = pink(L.n, seed)
        w = fft_filt(w, 'lp', 1200, 2)
        t_ = L.t
        amp = 0.62 + 0.22 * np.sin(TAU * 5 * t_ / MENU_T + c) + \
              0.16 * np.sin(TAU * 7 * t_ / MENU_T + 1.1 + c * 2)
        L.buf[c] += w * np.clip(amp, 0.15, None) * 0.075
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
        lo, hi = (1500.0, 5000.0) if rng.random() < 0.75 else (700.0, 2400.0)
        b_ = filt(noise(m, int(rng.integers(1, 1 << 30))), 'bp', (lo, hi), 2)
        b_ *= env_exp(m, 0.004, 0.0004)
        L.add(t, b_ * float(rng.uniform(0.15, 1.0)) * 0.085,
              pan=float(rng.uniform(-0.85, 0.85)))
    # --- solo cello answers (sparse, brooding) -----------------------------
    cello = [(0, 1.0, 1.8, 146.83), (1, 2.0, 1.4, 174.61), (3, 0.0, 2.0, 164.81),
             (6, 2.0, 1.6, 130.81), (10, 1.0, 2.0, 98.00), (14, 2.0, 1.8, 174.61),
             (18, 2.5, 1.4, 130.81)]
    for i, (b, beat, d, f) in enumerate(cello):
        L.add(tmen(b, beat), cello_note(f, d, attack=0.26, release=min(0.9, d * 0.5),
                                        lvl=0.42, seed=i * 13), pan=-0.34)
    # --- string pads + low choir, one chord per bar ------------------------
    for b in range(MENU_BARS):
        c = CH[MENU_CH[b]]
        pe, he, ce, te = (env_of(MENU_PAD_E, b), env_of(MENU_HRN_E, b),
                          env_of(MENU_CHO_E, b), env_of(MENU_TMP_E, b))
        L.add(tmen(b, 0), pad_st(c['pad'], MENU_BAR / SR + 1.4, attack=1.05,
                                 release=1.7, fc=2500, lvl=0.46 * pe, seed=b,
                                 spread=0.85))
        if b % 2 == 0:
            L.add(tmen(b, 0), pan2(choir_note(c['bass'], 2 * MENU_BAR / SR + 1.4,
                                               attack=1.7, release=2.2,
                                               lvl=0.42 * ce, seed=611 + b,
                                               formants=(530, 900, 2250),
                                               gains=(8, 5, -5), rolloff=1.55,
                                               lp=2600), 0.0))
        # soft timpani heartbeat: downbeat + backbeat
        L.add(tmen(b, 0), timpani(c['bass'], lvl=0.30 * te, seed=b * 17, dur=3.0))
        L.add(tmen(b, 2), timpani(c['bass'], lvl=0.16 * te, seed=b * 17 + 1, dur=2.6))
    # --- distant horn call in the intro (anticipates the anthem) -----------
    L.add(tmen(2, 0), brass(440.00, 2 * MENU_BAR / SR, lvl=0.20, attack=1.3,
                            release=2.2, seed=501, lp=1700, pan=0.30, bright=0.25,
                            oct_down=0.5, vib_depth=0.0025))
    # --- great-bell tolls on the phrase downbeats (attacks + colour) -------
    for b, lvl, f in ((4, 0.15, 293.66), (12, 0.17, 293.66), (18, 0.11, 392.00)):
        L.add(tmen(b, 0), pan2(toll(f, lvl, seed=300 + b), -0.18))
    # --- the horn anthem ---------------------------------------------------
    for off, table in ((4, MEL_M1), (12, MEL_M2)):
        for i, notes in enumerate(table):
            b = off + i
            he = env_of(MENU_HRN_E, b)
            if he < 0.02:
                continue
            c = CH[MENU_CH[b]]
            for j, (beat, dl, f) in enumerate(notes):
                d = dl * MENU_BEAT / SR
                L.add(tmen(b, beat), brass(f, d + 0.6, lvl=0.95 * he,
                                           attack=0.16, release=0.55,
                                           seed=b * 23 + j, lp=3600, pan=0.10,
                                           bright=0.7, oct_down=0.30))
                if b >= 12:                 # second statement: strings + choir
                    L.add(tmen(b, beat), solo_string(f, d + 0.6, lvl=0.20 * he,
                                                     attack=0.22, release=0.55,
                                                     pan=-0.28, seed=b * 23 + j + 7))
                    L.add(tmen(b, beat), pan2(choir_note(f * 2, d + 0.7,
                                                          attack=0.35, release=0.6,
                                                          lvl=0.055 * he,
                                                          seed=1701 + b + j,
                                                          lp=5200), 0.25))
    mix = L.buf
    mix = mix - np.mean(mix, axis=1, keepdims=True)
    ir = make_ir(2.2, 0.7, 5200, 150, 0.03, 405)
    mix = circ_rev(mix, ir, wet=0.26)
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
    """Quiet vale ambience with the war-march world at the horizon: a distant
    lone horn call and faint far-off low drum pulses, buried under the bed."""
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
    ev.add(41.0, pan2(bell * 0.065, -0.25))
    # --- distant lone horn call (far over the vale, mixed way under) --------
    HORN_CALL = [(9.0, 3.2, 293.66), (12.4, 2.0, 349.23), (14.6, 4.2, 293.66),
                 (45.0, 3.0, 261.63), (48.2, 2.4, 329.63), (50.8, 4.6, 293.66)]
    for i, (t0, d, f) in enumerate(HORN_CALL):
        s = brass(f, d, lvl=0.038 if i < 3 else 0.034, attack=0.55, release=1.4,
                  seed=900 + i, lp=1500, pan=0.34 if i < 3 else -0.30,
                  bright=0.2, oct_down=0.45, vib_depth=0.0022)
        ev.add(t0, s)
    # --- faint far-off low drum pulses (a march on the horizon) -------------
    for k, t0 in enumerate((4.0, 16.0, 28.0, 40.0, 52.0, 64.0)):
        ev.add(t0, taiko(lvl=0.046 if k % 2 == 0 else 0.036, seed=950 + k, big=True))
        ev.add(t0 + 0.55, taiko(lvl=0.028, seed=960 + k, big=False))
    # --- space --------------------------------------------------------------
    evm = ev.buf - np.mean(ev.buf, axis=1, keepdims=True)
    ir = make_ir(3.2, 0.9, 3500, 150, 0.05, 561)
    evm = circ_rev(evm, ir, wet=0.55)
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
    mono_tgt = MONO_TGT.get(name, MONO_RMS_TGT)
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
        err = m['mrms'] - mono_tgt
        if err > 0.15 or (err < -0.15 and -err <= head):
            y = y * db(-err)                # trim bed level within peak headroom
            continue
        if m['rms'] > NATIVE_RMS_MAX and err <= 0.15:
            y = y * db(-0.1)                # nudge under verify.py's native RMS cap
            continue
        break
    st = ffprobe(ogg)
    print(f"{name:8s} dur={st['dur']:.3f}s ch={st['ch']} native: peak={m['pk']:6.2f} "
          f"tp={m['tp']:6.2f} rms={m['rms']:6.2f} | mono(-ac 1): peak={m['mpk']:6.2f} "
          f"rms={m['mrms']:6.2f} lufs={m['lufs']:6.2f} | spec={dmin}-{dmax}s")
    ok = (st['dur'] >= dmin - 0.5 and st['dur'] <= dmax + 0.5
          and m['mpk'] <= -1.0 and m['tp'] <= -1.0
          and m['mrms'] <= -18.0 and -19.2 <= m['mrms']     # QA gate + target window
          and m['rms'] <= NATIVE_RMS_MAX and -23.0 <= m['rms']
          and m['pk'] <= -1.0)               # native contract ceilings
    return ok


if __name__ == '__main__':
    os.makedirs(WAV, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    names = sys.argv[1:] or list(BUILDERS)
    bad = [n for n in names if not render(n)]
    print('ALL PASS' if not bad else 'FAILED: ' + ', '.join(bad))
    sys.exit(1 if bad else 0)
