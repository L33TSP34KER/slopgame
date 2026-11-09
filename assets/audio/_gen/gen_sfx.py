#!/usr/bin/env python3
"""EMBERFALL SFX synthesis. Everything generated from scratch (numpy/scipy)."""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from dsp import *

WAV = '/tmp/emberfall_wav'          # ephemeral per-call scratch (bash /tmp)
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sfx')
CEIL = db(-7.0)                     # 0.4467 -> decoded true peak stays under -6 dBFS


def place(dst, t0, sig):
    i = ns(t0)
    m = len(sig)
    j = min(i + m, len(dst))
    if j > i:
        dst[i:j] += sig[:j - i]


# ------------------------------------------------------------------ builders
def s_click():
    """UI click: soft wooden tick (modal wood block + tiny strike transient)."""
    n = ns(0.18)
    tr = filt(noise(n, 11), 'hp', 2600, 2) * env_exp(n, 0.0015, 0.0002)
    body = modal([1180, 2360, 3540, 5150], [1.0, 0.5, 0.26, 0.12],
                 [0.030, 0.022, 0.015, 0.010], n, seed=3)
    knock = modal([430], [0.55], [0.020], n, seed=4)
    y = 0.95 * body + 0.55 * tr + 0.65 * knock
    y = filt(y, 'lp', 9500, 2)
    return fades(y, 0.0005, 0.010)


def s_select():
    """Unit selected: parchment brush + light armour tap."""
    n = ns(0.42)
    cloth = filt(noise(n, 21), 'bp', (2400, 7500), 2) * env_exp(n, 0.045, 0.004)
    tap = modal([2400, 3850, 5400, 7100], [1.0, 0.6, 0.36, 0.2],
                [0.095, 0.075, 0.055, 0.042], n, seed=5)
    wood = modal([560, 1140, 1780], [0.7, 0.32, 0.18], [0.06, 0.045, 0.03], n, seed=6)
    y = 0.90 * tap + 0.55 * cloth + 0.70 * wood
    y = filt(y, 'hp', 260, 2)
    y = filt(y, 'lp', 11000, 2)
    y = rev(y, make_ir(0.30, 0.09, 7000, 300, 0.008, 31), 0.14)
    return fades(y, 0.0008, 0.020)


def s_command():
    """Order acknowledged: muted drum + short metal ring."""
    n = ns(0.55)
    drum = sine_sweep(175, 62, n) * env_exp(n, 0.10, 0.001)
    bodyn = filt(noise(n, 41), 'bp', (140, 600), 2) * env_exp(n, 0.05, 0.001)
    metal = modal([3050, 4600, 6650, 8200], [1.0, 0.58, 0.32, 0.18],
                  [0.13, 0.10, 0.07, 0.05], n, seed=42)
    metal = np.roll(metal, ns(0.008))
    metal[:ns(0.008)] = 0.0
    y = 1.0 * drum + 0.55 * bodyn + 0.45 * metal
    y = filt(y, 'lp', 12000, 2)
    y = rev(y, make_ir(0.35, 0.10, 6500, 250, 0.012, 43), 0.16)
    return fades(y, 0.0008, 0.030)


def s_error():
    """Can't-do-that: two low wooden knocks, soft and dark (never a beep)."""
    n = ns(0.52)
    y = np.zeros(n)
    for k, (t0, mul, det) in enumerate([(0.0, 1.0, 1.0), (0.15, 0.74, 0.86)]):
        m = ns(0.40)
        kn = modal([300 * det, 610 * det, 940 * det, 1420 * det],
                   [1.0, 0.48, 0.26, 0.12], [0.055, 0.040, 0.030, 0.020], m, seed=51 + k)
        tr = filt(noise(m, 55 + k), 'hp', 1500, 2) * env_exp(m, 0.002, 0.0003)
        place(y, t0, (kn + 0.32 * tr) * mul)
    y = filt(y, 'lp', 4200, 2)
    y = filt(y, 'hp', 70, 2)
    y = rev(y, make_ir(0.30, 0.08, 4000, 150, 0.010, 53), 0.12)
    return fades(y, 0.0008, 0.030)


def s_gold():
    """Coins into purse: six bright metallic grains + soft purse thump."""
    n = ns(0.75)
    y = np.zeros(n)
    rng = np.random.default_rng(121)
    for i, t0 in enumerate([0.0, 0.055, 0.105, 0.175, 0.25, 0.33]):
        m = ns(0.32)
        det = float(rng.uniform(0.94, 1.07))
        amp = float(rng.uniform(0.6, 1.0)) * (1.0 - 0.05 * i)
        c = modal([2850 * det, 4250 * det, 6100 * det, 8300 * det],
                  [1.0, 0.66, 0.42, 0.26], [0.085, 0.065, 0.050, 0.038], m, seed=122 + i)
        c += 0.35 * filt(noise(m, 130 + i), 'bp', (4000, 9000), 2) * env_exp(m, 0.010, 0.001)
        place(y, t0, c * amp * 0.6)
    m = ns(0.30)
    th = sine_sweep(105, 70, m) * env_exp(m, 0.06, 0.003)
    th += filt(noise(m, 140), 'lp', 700, 2) * env_exp(m, 0.04, 0.003)
    place(y, 0.40, th * 0.55)
    y = filt(y, 'hp', 600, 2)
    y = filt(y, 'lp', 13000, 2)
    y = rev(y, make_ir(0.30, 0.07, 8000, 400, 0.006, 141), 0.12)
    return fades(y, 0.0005, 0.030)


def s_build():
    """Hammer on wood, short."""
    n = ns(0.45)
    tr = filt(noise(n, 101), 'hp', 1200, 2) * env_exp(n, 0.0025, 0.0003)
    wood = modal([455, 910, 1420, 2050, 3150], [1.0, 0.58, 0.36, 0.22, 0.13],
                 [0.070, 0.055, 0.040, 0.030, 0.020], n, seed=102)
    thud = sine_sweep(140, 95, n) * env_exp(n, 0.045, 0.002)
    nail = modal([4300], [0.30], [0.05], n, seed=103) * env_exp(n, 0.05, 0.001)
    y = 0.95 * wood + 0.70 * tr + 0.60 * thud + 0.30 * nail
    y = filt(y, 'lp', 11000, 2)
    y = rev(y, make_ir(0.30, 0.08, 6500, 250, 0.008, 104), 0.15)
    return fades(y, 0.0006, 0.030)


def s_build_done():
    """Structure completes: rising 4-note chime (D5-F5-A5-D6) + settle thud."""
    n = ns(1.12)
    y = np.zeros(n)
    for i, (f, t0) in enumerate([(587.33, 0.0), (698.46, 0.075),
                                 (880.0, 0.15), (1174.66, 0.225)]):
        m = n - ns(t0)
        b = modal([f, f * 2.01, f * 2.99, f * 4.07, f * 5.43],
                  [1.0, 0.52, 0.36, 0.22, 0.13],
                  [0.50, 0.38, 0.30, 0.22, 0.16], m, seed=111 + i)
        place(y, t0, b * (0.95 - 0.07 * i))
    m = ns(0.25)
    th = sine_sweep(120, 80, m) * env_exp(m, 0.06, 0.003)
    place(y, 0.0, th * 0.45)
    y = filt(y, 'hp', 250, 2)
    y = rev(y, make_ir(0.60, 0.22, 9000, 300, 0.020, 112), 0.30)
    return fades(y, 0.0008, 0.050)


def s_bow():
    """Bow release (Karplus-Strong) + arrow whoosh + distant thud."""
    n = ns(0.90)
    y = np.zeros(n)
    p = pluck(168.0, 0.24, damp=0.986, bright=0.65, seed=71, lp=4500)
    place(y, 0.0, p)
    wh = noise_morph(ns(0.14), [500, 1400, 3200], [1.0, 0.7, 0.4],
                     [0.05, 0.04, 0.03], q=1.6, seed=72, ons=[0.0, 0.012, 0.028])
    place(y, 0.006, wh * 0.55)
    m = ns(0.30)
    th = sine_sweep(85, 55, m) * env_exp(m, 0.09, 0.004)
    thn = filt(noise(m, 73), 'lp', 420, 2) * env_exp(m, 0.05, 0.004)
    place(y, 0.24, filt((0.9 * th + 0.7 * thn) * 0.6, 'lp', 500, 2))
    y = filt(y, 'hp', 60, 2)
    y = rev(y, make_ir(0.50, 0.16, 5000, 200, 0.020, 74), 0.22)
    return fades(y, 0.0008, 0.040)


# ------------------------------------------------------------------ tone engines
def horn_tone(f, n, bright=1.0, harm=90):
    """Bore/horn tone: detuned band-limited saw stack + sub octave + formants."""
    f0 = vib(f, n, rate=4.6, depth=0.004, delay=0.25)
    y = saw_f0(f0, n, nharm=harm, rolloff=1.05)
    y += 0.55 * saw_f0(f0 * 1.0035, n, nharm=harm, rolloff=1.15, ph0=1.1)
    y += 0.65 * np.sin(np.cumsum(TAU * f0 * 0.5) / SR)
    y = y / (np.max(np.abs(y)) + 1e-9)
    y = resonators(y, [240 * bright, 560 * bright, 1150 * bright],
                   [6 * bright, 3 * bright, -1], q=3.5)
    y = filt(y, 'lp', 1200 + 2200 * bright, 2)
    return np.tanh(1.4 * y)


def brass(f, n, atk=0.02, rel=0.12, fc0=900, fc1=3400, drive=1.6, harm=70,
          vibd=0.004, sub=0.0, fcdec=0.09, s_lvl=0.82, dcy=0.12):
    """Brass/hero voice: saw stack through a brightening filter + soft drive."""
    f0 = vib(f, n, 5.6, vibd, 0.14)
    y = saw_f0(f0, n, nharm=harm, rolloff=1.0)
    if sub > 0:
        y += sub * np.sin(np.cumsum(TAU * f0 * 0.5) / SR)
    y = y / (np.max(np.abs(y)) + 1e-9)
    fc = fc0 + (fc1 - fc0) * np.exp(-tt(n) / fcdec)
    y = svf_lp(y, fc, q=0.8)
    y = np.tanh(drive * y)
    e = env_adsr(n, atk, dcy, s_lvl, rel)
    return y * e


def strings(notes, d, attack=0.25, release=0.6, fc=3000, lvl=1.0):
    """Sustained string-chord pad: list of f (Hz) -> mono buffer of length ns(d)."""
    m = ns(d)
    ch = np.zeros(m)
    for i, f in enumerate(notes):
        ch += saw(f, m, ph=0.4 * i, rolloff=1.3)
        ch += 0.5 * saw(f * 1.0028, m, ph=1.9 + i, rolloff=1.4)
    ch = filt(ch, 'lp', fc, 2)
    ch *= env_swell(m, attack, release, 1.0)
    return ch * (lvl / max(len(notes), 1))


# ------------------------------------------------------------------ builders (12)
def s_sword():
    """Blade bites flesh with a metal ring."""
    n = ns(0.75)
    clang = modal([1730, 2610, 4120, 5970, 7650], [1.0, 0.72, 0.48, 0.30, 0.18],
                  [0.16, 0.13, 0.10, 0.07, 0.05], n, seed=61)
    strike = filt(noise(n, 62), 'bp', (1800, 9500), 2) * env_exp(n, 0.004, 0.0004)
    flesh = filt(noise(n, 63), 'lp', 850, 2) * env_exp(n, 0.045, 0.002)
    thud = sine_sweep(120, 78, n) * env_exp(n, 0.05, 0.002)
    y = 0.90 * clang + 0.80 * strike + 0.75 * flesh + 0.60 * thud
    m = ns(0.35)
    scrape = filt(noise(m, 64), 'bp', (3000, 8500), 2) * env_exp(m, 0.07, 0.02)
    place(y, 0.014, scrape * 0.35)
    y = filt(y, 'hp', 90, 2)
    y = rev(y, make_ir(0.5, 0.14, 7000, 250, 0.010, 65), 0.18)
    return fades(y, 0.0006, 0.040)


def s_magic():
    """Arcane whoosh: airy rising spectral sweep + shimmering tone cluster."""
    n = ns(1.02)
    layers = noise_morph(n, [400, 850, 1800, 3800, 7600],
                         [0.9, 1.0, 0.9, 0.65, 0.4], [0.55, 0.45, 0.36, 0.30, 0.24],
                         q=1.5, seed=81, ons=[0.0, 0.05, 0.10, 0.15, 0.20])
    y = layers * env_swell(n, 0.22, 0.50, 1.0)
    frise = 660.0 * (1.0 + 0.30 * np.clip(tt(n) / 0.7, 0, 1))
    shim = np.zeros(n)
    for k, g in [(1.0, 1.0), (1.5, 0.55), (2.0, 0.40), (3.0, 0.22)]:
        shim += g * np.sin(np.cumsum(TAU * frise * k) / SR + k)
    shim *= env_swell(n, 0.12, 0.55, 1.0)
    y = 0.85 * y + 0.45 * shim
    y = filt(y, 'hp', 280, 2)
    y = rev(y, make_ir(0.5, 0.16, 9000, 300, 0.012, 82), 0.35)
    return fades(y, 0.004, 0.060)


def s_holy():
    """Warm bell shimmer over an F-major pad (heal / level-up bed)."""
    n = ns(1.12)
    y = np.zeros(n)
    bell = modal([880, 1760, 2646, 3520, 4680, 5900],
                 [1.0, 0.55, 0.38, 0.26, 0.17, 0.11],
                 [0.55, 0.40, 0.30, 0.22, 0.16, 0.12], n, seed=91)
    place(y, 0.0, bell * 0.55)
    place(y, 0.14, bell[:n - ns(0.14)] * 0.32)
    pad = np.zeros(n)
    t_ = tt(n)
    for f, g in [(174.61, 1.0), (220.0, 0.8), (261.63, 0.7), (349.23, 0.5), (440.0, 0.34)]:
        pad += g * np.sin(TAU * f * t_ + 0.35 * np.sin(TAU * 0.55 * t_))
    pad *= env_swell(n, 0.10, 0.55, 1.0)
    y += 0.60 * filt(pad, 'lp', 3800, 2)
    sh = filt(noise(n, 92), 'bp', (5500, 11000), 2) * env_swell(n, 0.07, 0.60, 1.0)
    y += 0.10 * sh
    y = rev(y, make_ir(0.6, 0.24, 9000, 400, 0.020, 93), 0.35)
    return fades(y, 0.003, 0.050)


def s_chop():
    """Axe bites wood: crack transient + body thud + splinters."""
    n = ns(0.50)
    tr = filt(noise(n, 151), 'hp', 700, 2) * env_exp(n, 0.003, 0.0003)
    crack = modal([880, 1760, 2590, 3900, 5400], [1.0, 0.65, 0.45, 0.28, 0.16],
                  [0.055, 0.040, 0.030, 0.020, 0.015], n, seed=152)
    thud = sine_sweep(115, 72, n) * env_exp(n, 0.075, 0.002)
    y = 0.95 * crack + 0.85 * tr + 0.75 * thud
    rng = np.random.default_rng(153)
    for i in range(7):
        t0 = float(rng.uniform(0.03, 0.20))
        m = ns(0.05)
        lo = float(rng.uniform(2500, 5500))
        sp = filt(noise(m, 160 + i), 'bp', (lo, min(lo + 2500, 14000)), 2)
        place(y, t0, sp * env_exp(m, 0.012, 0.001) * float(rng.uniform(0.10, 0.30)))
    y = filt(y, 'lp', 12000, 2)
    y = rev(y, make_ir(0.35, 0.10, 7000, 300, 0.008, 154), 0.15)
    return fades(y, 0.0006, 0.030)


def s_death():
    """Short body fall: whoosh, heavy thud, faint armour clatter (no gore)."""
    n = ns(0.95)
    y = np.zeros(n)
    m = ns(0.16)
    wh = noise_morph(m, [700, 1600, 3000], [1.0, 0.6, 0.35], [0.10, 0.09, 0.08],
                     q=1.5, seed=171, ons=[0.0, 0.02, 0.04])
    wh *= np.linspace(0.2, 1.0, m) ** 1.5
    place(y, 0.0, wh * 0.35)
    m2 = ns(0.60)
    thud = sine_sweep(95, 52, m2) * env_exp(m2, 0.13, 0.004)
    body = filt(noise(m2, 172), 'lp', 650, 2) * env_exp(m2, 0.08, 0.004)
    rumble = filt(pink(m2, 173), 'lp', 180, 2) * env_exp(m2, 0.22, 0.010)
    place(y, 0.14, (0.9 * thud + 0.8 * body + 0.7 * rumble) * 0.80)
    for i, t0 in enumerate([0.17, 0.26]):
        m3 = ns(0.20)
        cl = modal([2300, 3700, 5200], [1.0, 0.5, 0.3], [0.05, 0.04, 0.03], m3, seed=174 + i)
        place(y, t0, cl * 0.16)
    y = filt(y, 'hp', 45, 2)
    y = rev(y, make_ir(0.5, 0.15, 4500, 200, 0.012, 175), 0.22)
    return fades(y, 0.002, 0.040)


def s_level_up():
    """Hero fanfare in D major, ~1.5 s."""
    n = ns(1.48)
    y = np.zeros(n)
    for i, (f, t0, d) in enumerate([(293.66, 0.00, 0.18), (369.99, 0.20, 0.18),
                                    (440.00, 0.40, 0.22), (587.33, 0.66, 0.72)]):
        m = ns(d + 0.14)
        tone = brass(f, m, atk=0.016, rel=0.10, fc0=1000, fc1=3400, drive=1.7, harm=70)
        place(y, t0, tone * (0.95 - 0.05 * i))
    place(y, 0.0, strings([146.83, 220.0, 293.66, 369.99], 1.10,
                          attack=0.03, release=0.5, fc=2600, lvl=0.9) * 0.40)
    m = ns(0.45)
    dr = sine_sweep(180, 70, m) * env_exp(m, 0.10, 0.002)
    dr += filt(noise(m, 181), 'bp', (150, 700), 2) * env_exp(m, 0.05, 0.002)
    place(y, 0.0, dr * 0.75)
    m = ns(0.85)
    bell = modal([1174.66, 2350, 3520], [1.0, 0.40, 0.22], [0.45, 0.30, 0.20], m, seed=183)
    place(y, 0.66, bell * 0.35)
    y = rev(y, make_ir(0.7, 0.30, 9000, 400, 0.020, 184), 0.30)
    return fades(y, 0.001, 0.050)


def s_alert():
    """Under attack: two low horn blasts + war drum, ~1.5 s."""
    n = ns(1.48)
    y = np.zeros(n)
    for i, (f, t0, d) in enumerate([(110.0, 0.00, 0.44), (146.83, 0.58, 0.54)]):
        m = ns(d + 0.16)
        tone = horn_tone(f, m, bright=1.0)
        place(y, t0, tone * env_adsr(m, 0.03, 0.14, 0.78, 0.12) * (1.0 - 0.1 * i))
    for t0 in (0.0, 0.58):
        m = ns(0.50)
        dr = sine_sweep(150, 58, m) * env_exp(m, 0.12, 0.002)
        dr += filt(noise(m, 191), 'lp', 500, 2) * env_exp(m, 0.06, 0.002)
        place(y, t0, dr * 0.95)
        place(y, t0 + 0.17, dr[:ns(0.30)] * 0.40)
    y = filt(y, 'hp', 65, 2)
    y = rev(y, make_ir(0.6, 0.20, 5000, 200, 0.020, 192), 0.30)
    return fades(y, 0.002, 0.050)


def s_horn():
    """Distant war horn: two long blasts over low drums, ~2.5 s."""
    n = ns(2.48)
    y = np.zeros(n)
    for f, t0, d, amp in [(73.42, 0.00, 1.30, 1.00), (110.0, 1.45, 0.65, 0.85)]:
        m = ns(d + 0.30)
        tone = horn_tone(f, m, bright=0.75)
        place(y, t0, tone * env_adsr(m, 0.10, 0.35, 0.70, 0.35) * amp)
    for t0, amp in [(0.0, 0.8), (1.45, 0.65)]:
        m = ns(0.70)
        dr = sine_sweep(120, 52, m) * env_exp(m, 0.18, 0.004)
        place(y, t0, filt(dr, 'lp', 320, 2) * amp)
    y = filt(y, 'lp', 2400, 2)
    y = filt(y, 'hp', 55, 2)
    y = rev(y, make_ir(1.0, 0.40, 3200, 120, 0.035, 201), 0.45)
    return fades(y, 0.004, 0.060)


def s_explosion():
    """Siege impact: downward spectral blast + sub boom + debris, ~1 s."""
    n = ns(1.05)
    sw = noise_morph(n, [9000, 4000, 1700, 600, 200],
                     [1.0, 0.9, 0.7, 0.5, 0.45], [0.30, 0.26, 0.22, 0.20, 0.18],
                     q=1.3, seed=211, ons=[0.0, 0.012, 0.030, 0.050, 0.070])
    boom = sine_sweep(135, 32, n) * env_exp(n, 0.30, 0.003)
    rumble = filt(pink(n, 212), 'lp', 140, 2) * env_exp(n, 0.42, 0.020)
    y = 0.9 * sw + boom + 0.7 * rumble
    rng = np.random.default_rng(214)
    for i in range(14):
        t0 = float(rng.uniform(0.08, 0.55))
        m = ns(0.07)
        lo = float(rng.uniform(900, 4000))
        hi = min(lo + float(rng.uniform(1500, 4500)), 15000.0)
        tick = filt(noise(m, 220 + i), 'bp', (lo, hi), 2) * env_exp(m, 0.015, 0.001)
        place(y, t0, tick * float(rng.uniform(0.10, 0.35)))
    y = filt(y, 'hp', 30, 2)
    y = rev(y, make_ir(0.6, 0.22, 7000, 80, 0.015, 213), 0.28)
    return fades(y, 0.001, 0.050)


def s_roar():
    """The Hollow King: sub growl + formant-shaped rasp, ~2 s."""
    n = ns(1.98)
    t_ = tt(n)
    f0 = (70.0 - 12.0 * np.clip(t_ / 1.4, 0, 1)) * \
         (1.0 + 0.035 * np.sin(TAU * 5.2 * t_) * np.clip((t_ - 0.1) / 0.5, 0, 1))
    sub = saw_f0(f0, n, nharm=30, rolloff=1.25)
    growl = saw_f0(f0 * 1.004, n, nharm=70, rolloff=1.0, ph0=0.7)
    rmod = np.clip(0.55 + 0.45 * np.sin(TAU * 27 * t_) + 0.25 * np.sin(TAU * 6.5 * t_),
                   0.0, 1.4)
    rasp = filt(noise(n, 221), 'bp', (700, 4200), 2) * rmod
    mix = sub + 0.75 * growl + 0.60 * rasp
    mix = resonators(mix, [350, 780, 2300], [9, 6, -3], q=6)
    e = env_adsr(n, 0.14, 0.40, 0.82, 0.45) * (1.0 + 0.10 * np.sin(TAU * 3.1 * t_))
    y = mix * e
    y += 0.10 * filt(noise(n, 222), 'hp', 1800, 2) * env_swell(n, 0.25, 0.60, 1.0)
    y = filt(y, 'lp', 7000, 2)
    y = filt(y, 'hp', 45, 2)
    y = np.tanh(1.35 * y / (np.max(np.abs(y)) + 1e-9)) * np.max(np.abs(y))
    y = rev(y, make_ir(0.8, 0.30, 5500, 150, 0.020, 223), 0.28)
    return fades(y, 0.010, 0.060)


def s_victory():
    """Triumphant D-major stinger, 4 s."""
    n = ns(4.0)
    y = np.zeros(n)
    mel = [(587.33, 0.00, 0.15), (587.33, 0.17, 0.15), (587.33, 0.34, 0.28),
           (440.00, 0.75, 0.15), (493.88, 0.92, 0.15), (440.00, 1.09, 0.30),
           (739.99, 1.50, 0.42), (587.33, 2.00, 1.55)]
    for i, (f, t0, d) in enumerate(mel):
        m = ns(d + 0.20)
        tone = brass(f, m, atk=0.018, rel=0.14, fc0=900, fc1=3600, drive=1.7, harm=70)
        place(y, t0, tone * (0.95 - 0.04 * i))
    for t0, d, notes, lvl in [
            (0.00, 0.75, [146.83, 185.00, 220.00, 293.66], 1.00),
            (0.75, 0.75, [220.00, 277.18, 329.63], 0.85),
            (1.50, 2.45, [146.83, 220.00, 293.66, 369.99, 440.00], 1.10)]:
        place(y, t0, strings(notes, d, attack=0.03, release=min(0.7, d * 0.45),
                             fc=3200, lvl=lvl) * 0.42)
    for t0, d, amp in [(0.00, 0.65, 1.0), (1.50, 2.30, 0.9)]:
        m = ns(d)
        b = brass(73.42, m, atk=0.02, rel=0.45, fc0=500, fc1=1600, drive=1.5,
                  harm=40, sub=0.4, fcdec=0.25, dcy=0.4)
        place(y, t0, b * 0.50 * amp)
    for t0, amp in [(0.0, 1.0), (1.5, 0.9)]:
        m = ns(0.70)
        dr = sine_sweep(150, 62, m) * env_exp(m, 0.18, 0.003)
        dr += filt(noise(m, 231), 'lp', 400, 2) * env_exp(m, 0.07, 0.003)
        place(y, t0, dr * 0.70 * amp)
    m = ns(0.50)
    place(y, 1.20, filt(noise(m, 241), 'hp', 4500, 2) * env_swell(m, 0.30, 0.20, 1.0) * 0.22)
    m = ns(2.0)
    bell = modal([1174.66, 2350, 3520, 4690], [1.0, 0.5, 0.3, 0.18],
                 [0.9, 0.6, 0.4, 0.3], m, seed=242)
    place(y, 1.50, bell * 0.30)
    y = rev(y, make_ir(1.2, 0.45, 8000, 300, 0.020, 243), 0.30)
    return fades(y, 0.001, 0.060)


def s_defeat():
    """Somber D-minor defeat stinger, 4 s (descending line + tolling bell)."""
    n = ns(4.0)
    y = np.zeros(n)
    for f, t0, d in [(293.66, 0.00, 0.85), (261.63, 0.85, 0.70),
                     (233.08, 1.55, 0.70), (220.00, 2.25, 1.45)]:
        m = ns(d + 0.25)
        tone = brass(f, m, atk=0.09, rel=0.35, fc0=450, fc1=1500, drive=1.15,
                     harm=50, fcdec=0.2, dcy=0.3)
        place(y, t0, filt(tone, 'lp', 2400, 2) * 0.60)
    for t0, d, notes, lvl in [
            (0.00, 1.45, [146.83, 174.61, 220.00, 293.66], 1.00),
            (1.20, 1.45, [116.54, 174.61, 233.08], 0.90),
            (2.40, 1.60, [73.42, 146.83, 220.00, 293.66], 1.00)]:
        place(y, t0, strings(notes, d, attack=0.18, release=0.7, fc=2400, lvl=lvl) * 0.45)
    for t0, amp in [(0.0, 1.0), (2.4, 0.85)]:
        m = ns(0.80)
        dr = sine_sweep(120, 55, m) * env_exp(m, 0.22, 0.004)
        dr += filt(noise(m, 251), 'lp', 350, 2) * env_exp(m, 0.09, 0.004)
        place(y, t0, dr * 0.65 * amp)
    m = ns(1.6)
    bell = modal([220, 440, 660, 940], [1.0, 0.5, 0.3, 0.18],
                 [1.6, 1.1, 0.8, 0.6], m, seed=252)
    place(y, 2.40, filt(bell, 'lp', 3000, 2) * 0.35)
    y += filt(pink(n, 253), 'lp', 900, 2) * env_swell(n, 0.8, 1.0, 1.0) * 0.14
    y = rev(y, make_ir(1.4, 0.50, 4500, 120, 0.030, 254), 0.32)
    return fades(y, 0.004, 0.150)


# ------------------------------------------------------------------ spec table
# name -> (builder, target RMS dBFS, limiter gain cap, max seconds)
SPEC = {
    # UI / economy (tranche 1)
    'click':      (s_click,      -21.0, 2.5, 1.20),
    'select':     (s_select,     -19.5, 2.5, 1.20),
    'command':    (s_command,    -19.0, 3.0, 1.20),
    'error':      (s_error,      -19.5, 2.5, 1.20),
    'gold':       (s_gold,       -19.5, 2.5, 1.20),
    'build':      (s_build,      -19.5, 2.5, 1.20),
    'build-done': (s_build_done, -19.0, 3.0, 1.20),
    'bow':        (s_bow,        -19.0, 3.0, 1.20),
    # combat / magic / world
    'sword':      (s_sword,      -18.5, 3.5, 1.20),
    'magic':      (s_magic,      -18.5, 3.5, 1.20),
    'holy':       (s_holy,       -18.5, 3.5, 1.20),
    'chop':       (s_chop,       -18.5, 3.5, 1.20),
    'death':      (s_death,      -19.0, 3.5, 1.20),
    'explosion':  (s_explosion,  -19.0, 4.0, 1.20),
    # events / stingers
    'level-up':   (s_level_up,   -16.5, 4.0, 1.55),
    'alert':      (s_alert,      -16.5, 4.0, 1.55),
    'horn':       (s_horn,       -17.0, 4.0, 2.55),
    'roar':       (s_roar,       -17.0, 4.0, 2.05),
    'victory':    (s_victory,    -16.5, 4.0, 4.10),
    'defeat':     (s_defeat,     -16.5, 4.0, 4.10),
}


def encode(wav_path, ogg_path, q=6):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav_path,
                    '-c:a', 'libvorbis', '-q:a', str(q), ogg_path], check=True)


def render(name, quiet=False):
    func, trms, ghi, maxdur = SPEC[name]
    x = np.asarray(func(), dtype=float)
    x = x - np.mean(x)
    assert np.max(np.abs(x)) > 1e-6, f'{name}: silent synthesis'
    y = balance_chain(x, trms, CEIL, g_hi=ghi, hp=20, fade=(0.0008, 0.006))
    y = fix_peak(y, CEIL)
    dur = len(y) / SR
    assert dur <= maxdur + 1e-6, f'{name}: {dur:.3f}s > {maxdur}s'
    wav = os.path.join(WAV, name + '.wav')
    ogg = os.path.join(OUT, name + '.ogg')
    write_wav(wav, y)
    encode(wav, ogg)
    # lossy codecs overshoot: re-scale until BOTH sample peak and true peak are safe
    tp = -99.0
    for _ in range(5):
        xdec = read_pcm_f32(ogg)
        ln = loudnorm_measure(ogg)
        tp = ln['tp'] if ln else peak_db(xdec)
        worst = max(peak_db(xdec), tp)
        if worst <= -6.2:
            break
        y = y * db(-6.4 - worst)
        write_wav(wav, y)
        encode(wav, ogg)
    st = ffprobe(ogg)
    xdec = read_pcm_f32(ogg)
    p, r, dc = peak_db(xdec), rms_db(xdec), float(np.mean(xdec))
    ok = (st['codec'] == 'vorbis' and st['ch'] == 1 and st['sr'] == 44100
          and p <= -6.0 and tp <= -6.0 and r > -50 and abs(dc) <= 0.002
          and st['dur'] <= maxdur + 0.06)
    if not quiet:
        print(f"{name:12s} dur={st['dur']:.3f}s peak={p:6.2f} tp={tp:6.2f} "
              f"rms={r:6.2f} dc={dc:+.5f} {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == '__main__':
    os.makedirs(WAV, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    names = sys.argv[1:] or list(SPEC)
    bad = [n for n in names if not render(n)]
    print('ALL PASS' if not bad else 'FAILED: ' + ', '.join(bad))
    sys.exit(1 if bad else 0)
