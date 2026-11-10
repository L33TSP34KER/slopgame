#!/usr/bin/env python3
"""EMBERFALL SFX synthesis (v2 — researched overhaul).

Two-source design, per the 2024-26 sound-design literature:
  * layered structure everywhere: ATTACK (0.5-2 ms transient) -> BODY
    (modal / FM / Karplus-Strong) -> TAIL (frequency-dependent IR reverb);
  * sfxr-style downward frequency ramps on impacts ("why it works": a fast
    pitch drop reads as weight, see drpetter.se/project_sfxr);
  * 2-op FM with a decaying modulation index for struck metal / bells —
    bright inharmonic attack that mellows, unlike a static modal ring;
  * tasteful tanh saturation for impact edge (weight without loudness);
  * CC0 foley layers (Kenney, CC0 1.0 — see fetch_cc0.py) mixed UNDER the
    synthesis, never instead of it, so the pack stays coherent.

Everything is still generated/mixed from scratch by numpy+scipy; the layers
only add real-world detail. License record: assets/audio/_gen/cc0/.
"""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from dsp import *
from cc0 import load as layer

WAV = '/tmp/emberfall_wav'          # ephemeral per-call scratch (bash /tmp)
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sfx')
CEIL = db(-7.0)                     # 0.4467 -> decoded true peak stays under -6 dBFS


def place(dst, t0, sig, tail_fade=0.006):
    i = ns(t0)
    m = len(sig)
    j = min(i + m, len(dst))
    if j > i:
        seg = sig[:j - i]
        if j - i < m:               # truncation would click: fade the cut
            seg = np.array(seg, dtype=float, copy=True)
            f = min(ns(tail_fade), len(seg))
            if f > 0:
                seg[-f:] *= np.cos(np.linspace(0, np.pi / 2, f)) ** 2
        dst[i:j] += seg


def bell_parts(d):
    """FM struck-bell partial recipe (ratio, amp, decay tau, modulator ratio)."""
    return [(1.00, 1.00, d, 1.41), (2.01, 0.50, d * 0.75, 2.77),
            (2.99, 0.34, d * 0.55, 1.73), (4.07, 0.22, d * 0.42, 3.41),
            (5.43, 0.13, d * 0.30, 4.13)]


# ------------------------------------------------------------------ builders
def s_click():
    """UI click: soft wooden tick — 0.6 ms transient + modal wood + warm sat."""
    n = ns(0.18)
    tr = filt(noise(n, 11), 'hp', 3200, 2) * env_exp(n, 0.0010, 0.0004)
    body = modal([1180, 2360, 3540, 5150], [1.0, 0.5, 0.26, 0.12],
                 [0.030, 0.022, 0.015, 0.010], n, seed=3)
    knock = modal([430], [0.55], [0.020], n, seed=4)
    y = 0.95 * body + 0.55 * tr + 0.65 * knock
    y = soft_sat(1.25 * y, 1.5, asym=0.10)
    y = filt(y, 'lp', 9500, 2)
    return fades(y, 0.0005, 0.010)


def s_select():
    """Unit selected: parchment brush (CC0 cloth) + light armour tap + wood."""
    n = ns(0.42)
    cloth = filt(noise(n, 21), 'bp', (2400, 7500), 2) * env_exp(n, 0.028, 0.003)
    tap = modal([2400, 3850, 5400, 7100], [1.0, 0.6, 0.36, 0.2],
                [0.095, 0.075, 0.055, 0.042], n, seed=5)
    wood = modal([560, 1140, 1780], [0.7, 0.32, 0.18], [0.06, 0.045, 0.03], n, seed=6)
    y = 0.90 * tap + 0.55 * cloth + 0.70 * wood
    place(y, 0.0, layer('cloth', 0.45))          # CC0 real parchment swish
    y = soft_sat(1.15 * y, 1.3)
    y = filt(y, 'hp', 260, 2)
    y = filt(y, 'lp', 11000, 2)
    y = rev(y, make_ir(0.30, 0.09, 7000, 300, 0.008, 31), 0.14)
    return fades(y, 0.0008, 0.020)


def s_command():
    """Order acknowledged: punchy muted drum (fast ramp down = sfxr 'weight')
    + real muted-metal ring (CC0) under a short synth metal modal."""
    n = ns(0.55)
    click = filt(noise(n, 45), 'hp', 1800, 2) * env_exp(n, 0.0007, 0.0003)
    drum = sine_sweep(190, 58, n) * env_exp(n, 0.085, 0.0006)
    bodyn = filt(noise(n, 41), 'bp', (140, 600), 2) * env_exp(n, 0.05, 0.001)
    metal = modal([3050, 4600, 6650, 8200], [1.0, 0.58, 0.32, 0.18],
                  [0.13, 0.10, 0.07, 0.05], n, seed=42)
    y = 1.0 * drum + 0.60 * click + 0.55 * bodyn + 0.28 * metal
    place(y, 0.005, layer('tin-ring', 0.85))      # CC0 real muted ring
    y = soft_sat(1.3 * y, 1.6, asym=0.08)
    y = filt(y, 'lp', 12000, 2)
    y = rev(y, make_ir(0.35, 0.10, 6500, 250, 0.012, 43), 0.16)
    return fades(y, 0.0008, 0.030)


def s_error():
    """Can't-do-that: two low wooden knocks with an sfxr-style downward pitch
    ramp (reads as 'weight/thunk', never as a beep)."""
    n = ns(0.52)
    y = np.zeros(n)
    for k, (t0, mul, det) in enumerate([(0.0, 1.0, 1.0), (0.15, 0.74, 0.86)]):
        m = ns(0.40)
        kn = modal([300 * det, 610 * det, 940 * det, 1420 * det],
                   [1.0, 0.48, 0.26, 0.12], [0.055, 0.040, 0.030, 0.020], m, seed=51 + k)
        bend = sine_sweep(560 * det, 360 * det, m) * env_exp(m, 0.032, 0.001)
        tr = filt(noise(m, 55 + k), 'hp', 1500, 2) * env_exp(m, 0.0012, 0.0004)
        place(y, t0, (kn + 0.45 * bend + 0.32 * tr) * mul)
    y = soft_sat(1.2 * y, 1.4, asym=0.14)
    y = filt(y, 'lp', 4200, 2)
    y = filt(y, 'hp', 70, 2)
    y = rev(y, make_ir(0.30, 0.08, 4000, 150, 0.010, 53), 0.12)
    return fades(y, 0.0008, 0.030)


def s_gold():
    """Coins into purse: six bright metallic grains + CC0 real coin jingle
    (layers underneath) + soft purse thump."""
    n = ns(0.75)
    y = np.zeros(n)
    place(y, 0.0, layer('coins', 0.75))           # CC0 real coins (backdrop)
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
    y = soft_sat(1.25 * y, 1.4)
    y = filt(y, 'hp', 600, 2)
    y = filt(y, 'lp', 13000, 2)
    y = rev(y, make_ir(0.30, 0.07, 8000, 400, 0.006, 141), 0.12)
    return fades(y, 0.0005, 0.030)


def s_build():
    """Hammer on wood, short: real strike (CC0 wood-light) over synth modal
    wood + thud; 0.7 ms transient keeps the attack honest."""
    n = ns(0.45)
    tr = filt(noise(n, 101), 'hp', 1400, 2) * env_exp(n, 0.0008, 0.0003)
    wood = modal([455, 910, 1420, 2050, 3150], [1.0, 0.58, 0.36, 0.22, 0.13],
                 [0.070, 0.055, 0.040, 0.030, 0.020], n, seed=102)
    thud = sine_sweep(150, 92, n) * env_exp(n, 0.045, 0.0015)
    nail = modal([4300], [0.30], [0.05], n, seed=103) * env_exp(n, 0.05, 0.001)
    y = 0.85 * wood + 0.70 * tr + 0.60 * thud + 0.30 * nail
    place(y, 0.0, layer('wood-light', 0.85))      # CC0 real hammer-on-wood
    y = soft_sat(1.3 * y, 1.6, asym=0.10)
    y = filt(y, 'lp', 11000, 2)
    y = rev(y, make_ir(0.30, 0.08, 6500, 250, 0.008, 104), 0.15)
    return fades(y, 0.0006, 0.030)


def s_build_done():
    """Structure completes: rising 4-note chime (D5-F5-A5-D6) in FM bell tones
    (inharmonic partials = real bell, not a beep) + CC0 bell on the last
    strike + settle thud."""
    n = ns(1.12)
    y = np.zeros(n)
    for i, (f, t0) in enumerate([(587.33, 0.0), (698.46, 0.075),
                                 (880.0, 0.15), (1174.66, 0.225)]):
        m = n - ns(t0)
        b = fm_partials(m, f, bell_parts(0.50), index=5.5, i_tau=0.022)
        place(y, t0, b * (0.95 - 0.07 * i))
    place(y, 0.225, layer('bell', 0.50))          # CC0 real bell shimmer
    m = ns(0.25)
    th = sine_sweep(120, 80, m) * env_exp(m, 0.06, 0.003)
    place(y, 0.0, th * 0.45)
    y = soft_sat(1.15 * y, 1.25)
    y = filt(y, 'hp', 250, 2)
    y = rev(y, make_ir(0.60, 0.22, 9000, 300, 0.020, 112), 0.30)
    return fades(y, 0.0008, 0.050)


def s_bow():
    """Bow release: brighter Karplus-Strong string + string-slap transient +
    arrow whoosh + distant thud."""
    n = ns(0.90)
    y = np.zeros(n)
    p = pluck(168.0, 0.24, damp=0.988, bright=0.80, seed=71, lp=6500)
    place(y, 0.0, p)
    m = ns(0.03)
    slap = filt(noise(m, 711), 'hp', 2200, 2) * env_exp(m, 0.0012, 0.0004)
    place(y, 0.0, slap * 0.45)                    # fingers/string release snap
    wh = noise_morph(ns(0.14), [500, 1400, 3200], [1.0, 0.7, 0.4],
                     [0.05, 0.04, 0.03], q=1.6, seed=72, ons=[0.0, 0.012, 0.028])
    place(y, 0.006, wh * 0.55)
    m = ns(0.30)
    th = sine_sweep(85, 55, m) * env_exp(m, 0.09, 0.004)
    thn = filt(noise(m, 73), 'lp', 420, 2) * env_exp(m, 0.05, 0.004)
    place(y, 0.24, filt((0.9 * th + 0.7 * thn) * 0.7, 'lp', 500, 2))
    y = soft_sat(1.2 * y, 1.35)
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
    """Blade hits flesh/metal: 1 ms strike transient + FM clang (decaying
    modulation index — bright attack, mellow tail) + CC0 real blade whoosh,
    metal clang and leather thud layered under the synth."""
    n = ns(0.75)
    y = np.zeros(n)
    clang = modal([1730, 2610, 4120, 5970, 7650], [1.0, 0.72, 0.48, 0.30, 0.18],
                  [0.16, 0.13, 0.10, 0.07, 0.05], n, seed=61)
    fm_clang = fm_tone(n, freq_sweep(1900, 1580, n), ratio=1.41, index=7.0,
                       i_tau=0.05, env=env_exp(n, 0.14, 0.002))
    strike = filt(noise(n, 62), 'bp', (2200, 11000), 2) * env_exp(n, 0.0010, 0.0004)
    flesh = filt(noise(n, 63), 'lp', 850, 2) * env_exp(n, 0.045, 0.002)
    thud = sine_sweep(120, 78, n) * env_exp(n, 0.05, 0.002)
    y = 0.55 * clang + 0.75 * fm_clang + 0.85 * strike + 0.75 * flesh + 0.60 * thud
    m = ns(0.35)
    scrape = filt(noise(m, 64), 'bp', (3000, 8500), 2) * env_exp(m, 0.07, 0.02)
    place(y, 0.014, scrape * 0.35)
    place(y, 0.0, layer('knife-swipe', 0.55))     # CC0 blade whoosh
    place(y, 0.005, layer('sword-metal', 1.10))   # CC0 real metal clang
    place(y, 0.012, layer('leather', 0.40))       # CC0 flesh/leather thud
    y = soft_sat(1.35 * y, 1.7, asym=0.08)
    y = filt(y, 'lp', 12000, 2)      # tame sat harmonics -> no ISP overshoot
    y = filt(y, 'hp', 90, 2)
    y = rev(y, make_ir(0.5, 0.14, 7000, 250, 0.010, 65), 0.18)
    return fades(y, 0.0006, 0.040)


def s_magic():
    """Arcane whoosh: layered spectral sweep + FM shimmer riding the rise +
    sparkle chirps (short upward ramps read as 'magic dust')."""
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
    shim = 0.75 * shim + 0.35 * fm_tone(n, frise, ratio=1.5, index=3.0,
                                        i_tau=0.30) * env_swell(n, 0.12, 0.55, 1.0)
    y = 0.85 * y + 0.45 * shim
    for i, t0 in enumerate([0.10, 0.24, 0.38, 0.52]):   # sparkle grains
        m = ns(0.20)
        chirp = sine_sweep(900 + 300 * i, 3600 + 500 * i, m) * \
            env_exp(m, 0.05, 0.004)
        place(y, t0, chirp * 0.13)
    y = soft_sat(1.15 * y, 1.25)
    y = filt(y, 'hp', 280, 2)
    y = rev(y, make_ir(0.5, 0.16, 9000, 300, 0.012, 82), 0.35)
    return fades(y, 0.004, 0.060)


def s_holy():
    """Warm bell shimmer over an F-major pad: FM bell (inharmonic partials) +
    CC0 real bell layered underneath."""
    n = ns(1.12)
    y = np.zeros(n)
    bell = fm_partials(n, 880.0, bell_parts(0.55), index=5.0, i_tau=0.030)
    place(y, 0.0, bell * 0.55)
    place(y, 0.14, bell[:n - ns(0.14)] * 0.32)
    place(y, 0.0, layer('bell', 0.50))            # CC0 real warm bell
    pad = np.zeros(n)
    t_ = tt(n)
    for f, g in [(174.61, 1.0), (220.0, 0.8), (261.63, 0.7), (349.23, 0.5), (440.0, 0.34)]:
        pad += g * np.sin(TAU * f * t_ + 0.35 * np.sin(TAU * 0.55 * t_))
    pad *= env_swell(n, 0.10, 0.55, 1.0)
    y += 0.60 * filt(pad, 'lp', 3800, 2)
    sh = filt(noise(n, 92), 'bp', (5500, 11000), 2) * env_swell(n, 0.07, 0.60, 1.0)
    y += 0.10 * sh
    y = soft_sat(1.1 * y, 1.2)
    y = rev(y, make_ir(0.6, 0.24, 9000, 400, 0.020, 93), 0.35)
    return fades(y, 0.003, 0.050)


def s_chop():
    """Axe bites wood: 0.8 ms crack transient + body thud + splinters +
    CC0 real axe-bite layered under it all."""
    n = ns(0.50)
    tr = filt(noise(n, 151), 'hp', 900, 2) * env_exp(n, 0.0008, 0.0003)
    crack = modal([880, 1760, 2590, 3900, 5400], [1.0, 0.65, 0.45, 0.28, 0.16],
                  [0.055, 0.040, 0.030, 0.020, 0.015], n, seed=152)
    thud = sine_sweep(115, 72, n) * env_exp(n, 0.075, 0.002)
    y = 0.80 * crack + 0.75 * tr + 0.75 * thud
    place(y, 0.0, layer('axe-chop', 1.00))        # CC0 real axe in wood
    rng = np.random.default_rng(153)
    for i in range(7):
        t0 = float(rng.uniform(0.03, 0.20))
        m = ns(0.05)
        lo = float(rng.uniform(2500, 5500))
        sp = filt(noise(m, 160 + i), 'bp', (lo, min(lo + 2500, 14000)), 2)
        place(y, t0, sp * env_exp(m, 0.012, 0.001) * float(rng.uniform(0.10, 0.30)))
    y = soft_sat(1.35 * y, 1.7, asym=0.10)
    y = filt(y, 'lp', 12000, 2)
    y = rev(y, make_ir(0.35, 0.10, 7000, 300, 0.008, 154), 0.15)
    return fades(y, 0.0006, 0.030)


def s_death():
    """Short body fall: whoosh, heavy thud (CC0 real body-fall + leather
    under the synth), faint armour clatter — no gore."""
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
    place(y, 0.13, layer('body-fall', 1.00))      # CC0 real heavy fall
    place(y, 0.17, layer('leather', 0.35))        # CC0 armour/leather
    for i, t0 in enumerate([0.17, 0.26]):
        m3 = ns(0.20)
        cl = modal([2300, 3700, 5200], [1.0, 0.5, 0.3], [0.05, 0.04, 0.03], m3, seed=174 + i)
        place(y, t0, cl * 0.16)
    y = soft_sat(1.2 * y, 1.35)
    y = filt(y, 'hp', 45, 2)
    y = rev(y, make_ir(0.5, 0.15, 4500, 200, 0.012, 175), 0.22)
    return fades(y, 0.002, 0.040)


def s_level_up():
    """Hero fanfare in D major, ~1.5 s: brighter brass attack, FM bell on the
    final note, shimmer rise into it."""
    n = ns(1.48)
    y = np.zeros(n)
    for i, (f, t0, d) in enumerate([(293.66, 0.00, 0.18), (369.99, 0.20, 0.18),
                                    (440.00, 0.40, 0.22), (587.33, 0.66, 0.72)]):
        m = ns(d + 0.14)
        tone = brass(f, m, atk=0.014, rel=0.10, fc0=1000, fc1=3600, drive=1.8, harm=70)
        place(y, t0, tone * (0.95 - 0.05 * i))
    place(y, 0.0, strings([146.83, 220.0, 293.66, 369.99], 1.10,
                          attack=0.03, release=0.5, fc=2600, lvl=0.9) * 0.40)
    m = ns(0.45)
    dr = sine_sweep(180, 70, m) * env_exp(m, 0.10, 0.002)
    dr += filt(noise(m, 181), 'bp', (150, 700), 2) * env_exp(m, 0.05, 0.002)
    place(y, 0.0, dr * 0.75)
    m = ns(0.85)
    bell = fm_partials(m, 1174.66, bell_parts(0.45), index=5.0, i_tau=0.025)
    place(y, 0.66, bell * 0.40)
    m = ns(0.50)                                  # shimmer rise into the last note
    rise = filt(noise(m, 185), 'hp', 4500, 2) * env_swell(m, 0.34, 0.16, 1.0)
    place(y, 0.24, rise * 0.16)
    y = soft_sat(1.15 * y, 1.3)
    y = filt(y, 'lp', 14000, 2)
    y = rev(y, make_ir(0.7, 0.30, 9000, 400, 0.020, 184), 0.30)
    return fades(y, 0.001, 0.050)


def s_alert():
    """Under attack: two low horn blasts (with breath) + punchy war drums,
    ~1.5 s. Drum clicks give each hit a proper transient."""
    n = ns(1.48)
    y = np.zeros(n)
    for i, (f, t0, d) in enumerate([(110.0, 0.00, 0.44), (146.83, 0.58, 0.54)]):
        m = ns(d + 0.16)
        tone = horn_tone(f, m, bright=1.0)
        blast = tone * env_adsr(m, 0.03, 0.14, 0.78, 0.12)
        breath = filt(noise(m, 190 + i), 'bp', (600, 2600), 2) * \
            env_adsr(m, 0.05, 0.16, 0.55, 0.14)
        place(y, t0, (blast + 0.10 * breath) * (1.0 - 0.1 * i))
    for j, t0 in enumerate((0.0, 0.58)):
        m = ns(0.50)
        dr = sine_sweep(165, 55, m) * env_exp(m, 0.11, 0.0008)
        dr += filt(noise(m, 191), 'lp', 500, 2) * env_exp(m, 0.05, 0.001)
        ck = filt(noise(m, 193 + j), 'hp', 1400, 2) * env_exp(m, 0.0008, 0.0003)
        place(y, t0, (dr + 0.30 * ck) * 0.95)
        place(y, t0 + 0.17, dr[:ns(0.30)] * 0.40)
    y = soft_sat(1.25 * y, 1.5)
    y = filt(y, 'hp', 65, 2)
    y = rev(y, make_ir(0.6, 0.20, 5000, 200, 0.020, 192), 0.30)
    return fades(y, 0.002, 0.050)


def s_horn():
    """Distant war horn: two long bore blasts with breath over low drums,
    darker IR + low-pass for distance, ~2.5 s."""
    n = ns(2.48)
    y = np.zeros(n)
    for i, (f, t0, d, amp) in enumerate([(73.42, 0.00, 1.30, 1.00),
                                         (110.0, 1.45, 0.65, 0.85)]):
        m = ns(d + 0.30)
        tone = horn_tone(f, m, bright=0.75)
        env = env_adsr(m, 0.10, 0.35, 0.70, 0.35)
        breath = filt(noise(m, 200 + i), 'bp', (400, 2000), 2) * env
        place(y, t0, (tone + 0.12 * breath) * env * amp)
    for t0, amp in [(0.0, 0.8), (1.45, 0.65)]:
        m = ns(0.70)
        dr = sine_sweep(120, 52, m) * env_exp(m, 0.18, 0.004)
        place(y, t0, filt(dr, 'lp', 320, 2) * amp)
    y = filt(y, 'lp', 2400, 2)
    y = soft_sat(1.2 * y, 1.3)
    y = filt(y, 'hp', 55, 2)
    y = rev(y, make_ir(1.0, 0.40, 2600, 120, 0.035, 201), 0.50)
    return fades(y, 0.004, 0.060)


def s_explosion():
    """Siege impact, ~1 s: 0.6 ms crack transient + two-stage downward blast
    sweep (fast collapse = sfxr impact recipe) + sub boom + debris, all run
    through tanh saturation for grit before the IR tail."""
    n = ns(1.05)
    sw = noise_morph(n, [9000, 4000, 1700, 600, 200],
                     [1.0, 0.9, 0.75, 0.6, 0.55], [0.22, 0.20, 0.20, 0.20, 0.20],
                     q=1.3, seed=211, ons=[0.0, 0.010, 0.026, 0.045, 0.065])
    crack = filt(noise(n, 215), 'hp', 2500, 2) * env_exp(n, 0.0007, 0.0003)
    boom = sine_sweep(170, 34, n) * env_exp(n, 0.26, 0.0012)
    rumble = filt(pink(n, 212), 'lp', 140, 2) * env_exp(n, 0.42, 0.020)
    y = 0.85 * sw + 1.0 * crack + boom + 0.7 * rumble
    rng = np.random.default_rng(214)
    for i in range(14):
        t0 = float(rng.uniform(0.08, 0.55))
        m = ns(0.07)
        lo = float(rng.uniform(900, 4000))
        hi = min(lo + float(rng.uniform(1500, 4500)), 15000.0)
        tick = filt(noise(m, 220 + i), 'bp', (lo, hi), 2) * env_exp(m, 0.015, 0.001)
        place(y, t0, tick * float(rng.uniform(0.10, 0.35)))
    y = soft_sat(1.6 * y, 1.9)
    y = filt(y, 'lp', 11500, 2)
    y = filt(y, 'hp', 30, 2)
    y = rev(y, make_ir(0.6, 0.22, 7000, 80, 0.015, 213), 0.28)
    return fades(y, 0.001, 0.050)


def s_roar():
    """The Hollow King, ~2 s: sub growl + vowel glide (open->closed formant
    crossfade) + AM rasp + asymmetric saturation for heat."""
    n = ns(1.98)
    t_ = tt(n)
    f0 = (70.0 - 12.0 * np.clip(t_ / 1.4, 0, 1)) * \
         (1.0 + 0.035 * np.sin(TAU * 5.2 * t_) * np.clip((t_ - 0.1) / 0.5, 0, 1))
    sub = saw_f0(f0, n, nharm=30, rolloff=1.25) + \
        0.45 * np.sin(np.cumsum(TAU * f0 * 0.5) / SR)   # sub octave weight
    growl = saw_f0(f0 * 1.004, n, nharm=70, rolloff=1.0, ph0=0.7)
    rmod = np.clip(0.55 + 0.45 * np.sin(TAU * 27 * t_) + 0.25 * np.sin(TAU * 6.5 * t_),
                   0.0, 1.4)
    rmod *= 0.75 + 0.25 * np.sin(TAU * 38 * t_)          # granular AM rasp
    rasp = filt(noise(n, 221), 'bp', (700, 4200), 2) * rmod
    mix = sub + 0.75 * growl + 0.60 * rasp
    # vowel glide: open 'ah' -> closed 'oh' crossfade over the roar
    g = np.clip(t_ / 1.2, 0, 1)
    fa = resonators(mix, [430, 980, 2400], [9, 6, -3], q=6)
    fb = resonators(mix, [310, 720, 2100], [9, 6, -3], q=6)
    mix = (1.0 - g) * fa + g * fb
    e = env_adsr(n, 0.14, 0.40, 0.82, 0.45) * (1.0 + 0.10 * np.sin(TAU * 3.1 * t_))
    y = mix * e
    y += 0.10 * filt(noise(n, 222), 'hp', 1800, 2) * env_swell(n, 0.25, 0.60, 1.0)
    y = filt(y, 'lp', 7000, 2)
    y = filt(y, 'hp', 45, 2)
    y = soft_sat(1.9 * y / (np.max(np.abs(y)) + 1e-9), 1.9, asym=0.12) * np.max(np.abs(y))
    y = rev(y, make_ir(0.8, 0.30, 5500, 150, 0.020, 223), 0.28)
    return fades(y, 0.010, 0.060)


def s_victory():
    """Triumphant D-major stinger, 4 s: brass with a controlled brightness
    range, FM bells on the final chord, timpani-weight low drums, and the
    cymbial swell tamed so the whole thing sits warm instead of hissy."""
    n = ns(4.0)
    y = np.zeros(n)
    mel = [(587.33, 0.00, 0.15), (587.33, 0.17, 0.15), (587.33, 0.34, 0.28),
           (440.00, 0.75, 0.15), (493.88, 0.92, 0.15), (440.00, 1.09, 0.30),
           (739.99, 1.50, 0.42), (587.33, 2.00, 1.55)]
    for i, (f, t0, d) in enumerate(mel):
        m = ns(d + 0.20)
        tone = brass(f, m, atk=0.016, rel=0.14, fc0=900, fc1=3200, drive=1.7, harm=70)
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
        timp = sine_sweep(92, 46, ns(0.55)) * env_exp(ns(0.55), 0.22, 0.004)
        place(y, t0, dr * 0.70 * amp)
        place(y, t0, timp * 0.35 * amp)
    m = ns(0.50)                                   # tamed cymbial swell
    place(y, 1.20, filt(noise(m, 241), 'hp', 3800, 2) *
          env_swell(m, 0.30, 0.20, 1.0) * 0.13)
    m = ns(2.0)
    bell = fm_partials(m, 1174.66, bell_parts(0.9), index=5.0, i_tau=0.03)
    place(y, 1.50, bell * 0.34)
    y = soft_sat(1.12 * y, 1.25)
    y = filt(y, 'lp', 12000, 2)
    y = rev(y, make_ir(1.2, 0.45, 8000, 300, 0.020, 243), 0.30)
    return fades(y, 0.001, 0.060)


def s_defeat():
    """Somber D-minor defeat stinger, 4 s: descending line + FM tolling bell
    (long inharmonic decay) over dark strings."""
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
    m = ns(1.6)                                    # toll
    bell = fm_partials(m, 220.0, [(1.0, 1.0, 1.5, 1.41), (2.01, 0.5, 1.1, 2.7),
                                  (2.99, 0.3, 0.85, 3.3), (4.2, 0.16, 0.6, 1.7)],
                       index=4.5, i_tau=0.05)
    place(y, 2.40, filt(bell, 'lp', 3000, 2) * 0.38)
    y += filt(pink(n, 253), 'lp', 900, 2) * env_swell(n, 0.8, 1.0, 1.0) * 0.14
    y = soft_sat(1.1 * y, 1.2)
    y = rev(y, make_ir(1.4, 0.50, 4500, 120, 0.030, 254), 0.32)
    return fades(y, 0.004, 0.150)


# ------------------------------------------------------------------ spec table
# name -> (builder, target RMS dBFS, limiter gain cap, max seconds)
SPEC = {
    # UI / economy (tranche 1)
    # click's target is set +0.5 over the design value so the *decoded* file
    # (vorbis flush appends ~22 ms of silence that RMS windows include) lands
    # on -21 dBFS as measured by tools/qa/audio_review.py.
    'click':      (s_click,      -20.5, 3.2, 1.20),
    'select':     (s_select,     -19.5, 2.5, 1.20),
    'command':    (s_command,    -19.0, 3.0, 1.20),
    'error':      (s_error,      -19.5, 2.5, 1.20),
    'gold':       (s_gold,       -19.5, 2.5, 1.20),
    'build':      (s_build,      -19.5, 2.5, 1.20),
    'build-done': (s_build_done, -19.0, 3.0, 1.20),
    'bow':        (s_bow,        -19.0, 3.0, 1.20),
    # combat / magic / world
    'sword':      (s_sword,      -18.5, 4.5, 1.20),
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
