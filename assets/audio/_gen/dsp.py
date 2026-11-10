"""Shared DSP / synthesis toolkit for EMBERFALL audio pack (from scratch, numpy+scipy)."""
import numpy as np
from scipy import signal

SR = 44100
TAU = 2.0 * np.pi


# ---------------------------------------------------------------- basics
def db(x):
    return 10.0 ** (x / 20.0)


def db20(x):
    return 20.0 * np.log10(np.maximum(np.asarray(x, dtype=float), 1e-12))


def ns(sec):
    return int(round(sec * SR))


def tt(n):
    return np.arange(n) / SR


def rms(x):
    x = np.asarray(x, dtype=float)
    return float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0


def rms_db(x):
    return float(db20(rms(x)))


def peak(x):
    x = np.asarray(x, dtype=float)
    return float(np.max(np.abs(x))) if x.size else 0.0


def peak_db(x):
    return float(db20(peak(x)))


def norm_peak(x, target=1.0):
    p = peak(x)
    return x if p <= 0 else x * (target / p)


def noise(n, seed=0):
    return np.random.default_rng(seed).standard_normal(n)


def pink(n, seed=0):
    """1/f shaped noise via FFT (exactly n samples)."""
    w = noise(n, seed)
    X = np.fft.rfft(w)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    f[0] = f[1] if len(f) > 1 else 1.0
    X /= np.sqrt(f)
    y = np.fft.irfft(X, n=n)
    return y / (np.max(np.abs(y)) + 1e-12)


# ---------------------------------------------------------------- oscillators
def sine(f, n, ph=0.0):
    return np.sin(TAU * f * tt(n) + ph)


def freq_sweep(f0, f1, n, curve='exp'):
    """Per-sample instantaneous frequency from f0 to f1 (exp = sfxr-style ramp)."""
    t_ = tt(n)
    T = max(n - 1, 1) / SR
    if curve == 'exp' and f0 > 0 and f1 > 0:
        return f0 * (f1 / f0) ** (t_ / T)
    return f0 + (f1 - f0) * (t_ / T)


def sine_sweep(f0, f1, n, curve='exp'):
    ph = np.cumsum(TAU * freq_sweep(f0, f1, n, curve) / SR)
    return np.sin(ph)


def saw(f, n, ph=0.0, rolloff=1.0):
    """Band-limited additive saw at fixed f."""
    t_ = tt(n)
    y = np.zeros(n)
    for k in range(1, 200):
        if f * k >= SR * 0.45:
            break
        y += (1.0 / (k ** rolloff)) * np.sin(TAU * f * k * t_ + ph)
    return y * 0.5


def saw_f0(f0_arr, n, ph0=0.0, rolloff=1.0, nharm=120):
    """Band-limited saw with per-sample f0 (array of length n)."""
    y = np.zeros(n)
    fmax = SR * 0.45
    for k in range(1, nharm + 1):
        fk = f0_arr * k
        if np.max(fk) > fmax:
            break
        ph = np.cumsum(TAU * fk / SR) + ph0
        y += (1.0 / (k ** rolloff)) * np.sin(ph)
    return y * 0.5


def square_f0(f0_arr, n, nharm=80, rolloff=1.0):
    y = np.zeros(n)
    fmax = SR * 0.45
    for k in range(1, nharm * 2, 2):
        fk = f0_arr * k
        if np.max(fk) > fmax:
            break
        ph = np.cumsum(TAU * fk / SR)
        y += (1.0 / (k ** rolloff)) * np.sin(ph)
    return y * 0.5


def vib(f, n, rate=5.5, depth=0.006, delay=0.15):
    """f0 scalar/array with vibrato that fades in after `delay` seconds."""
    t_ = tt(n)
    ramp = np.clip((t_ - delay) / 0.4, 0.0, 1.0)
    f = np.asarray(f, dtype=float)
    return f * (1.0 + depth * ramp * np.sin(TAU * rate * t_))


# ---------------------------------------------------------------- modal / physical
def modal(freqs, amps, taus, n, phases=None, seed=0):
    """Sum of exponentially damped sinusoids (taus = amplitude time constant, s)."""
    rng = np.random.default_rng(seed)
    t_ = tt(n)
    y = np.zeros(n)
    for i, (f, a, tau) in enumerate(zip(freqs, amps, taus)):
        ph = float(rng.uniform(0, TAU)) if phases is None else phases[i]
        y += a * np.exp(-t_ / tau) * np.sin(TAU * f * t_ + ph)
    return y


def pluck(f, dur, damp=0.995, bright=0.5, seed=0, lp=0.0):
    """Karplus-Strong plucked string (block-recursive, circular delay line)."""
    n = ns(dur)
    N = max(int(round(SR / f)), 4)
    rng = np.random.default_rng(seed)
    prev = rng.standard_normal(N)
    if bright < 1.0:
        prev = signal.lfilter([1 - bright, bright], [1.0], prev)
    chunks = []
    remaining = n
    while remaining > 0:
        j = min(N, remaining)
        nxt = damp * 0.5 * (prev + np.roll(prev, 1))
        chunks.append(nxt[:j])
        prev = nxt
        remaining -= j
    y = np.concatenate(chunks)
    if lp > 0:
        y = filt(y, 'lp', lp, 2)
    return y


# ---------------------------------------------------------------- FM / saturation
def fm_tone(n, fc, ratio=2.0, index=6.0, i_tau=0.04, env=None):
    """2-op FM struck-tone (the DX7 "struck metal" recipe): carrier `fc`
    (scalar or per-sample array, so a freq_sweep() can drive it), modulator at
    fc*ratio, modulation index decaying with time constant i_tau — bright
    inharmonic attack that mellows into a near-pure tone. Multiply by `env`
    for a partial decay (bells) if given."""
    fc = np.broadcast_to(np.asarray(fc, dtype=float), (n,))
    im = np.cumsum(TAU * (fc * ratio) / SR)
    ic = np.cumsum(TAU * fc / SR)
    idx = index * np.exp(-tt(n) / max(i_tau, 1e-6))
    y = np.sin(ic + idx * np.sin(im))
    return y if env is None else y * env


def fm_partials(n, f0, parts, index=6.0, i_tau=0.03):
    """Stack of FM partials -> struck bell / metal bar.

    parts: list of (freq_ratio, amp, decay_tau, mod_ratio). Each partial is its
    own FM tone with a decaying index (attack brights) and a decaying
    amplitude (bell decay), which is what separates a real bell from a beep.
    """
    t_ = tt(n)
    y = np.zeros(n)
    for i, (r, a, tau, mr) in enumerate(parts):
        env = a * np.exp(-t_ / max(tau, 1e-6))
        y += fm_tone(n, f0 * r, ratio=mr, index=index * (0.8 + 0.08 * i),
                     i_tau=i_tau, env=env)
    return y


def soft_sat(x, drive=1.5, asym=0.0):
    """tanh saturation with ~unity small-signal gain. drive>1 adds harmonics
    (perceived weight/edge on impacts); asym adds even harmonics (tube-ish
    warmth) — DC from asymmetry is removed by balance_chain's mean removal."""
    y = drive * (np.asarray(x, dtype=float) + asym)
    return (np.tanh(y) - np.tanh(drive * asym)) / drive


# ---------------------------------------------------------------- filters
def _sos(kind, cutoff, order, sr=SR):
    if kind in ('bp', 'bandpass'):
        lo, hi = cutoff
        lo = max(lo, 20.0)
        hi = min(hi, sr * 0.49)
        return signal.butter(order, [lo, hi], btype='bandpass', fs=sr, output='sos')
    if kind in ('lp', 'lowpass'):
        return signal.butter(order, min(cutoff, sr * 0.49), btype='lowpass', fs=sr, output='sos')
    return signal.butter(order, max(cutoff, 15.0), btype='highpass', fs=sr, output='sos')


def filt(x, kind, cutoff, order=4, axis=-1):
    return signal.sosfilt(_sos(kind, cutoff, order), x, axis=axis)


def fft_filt(x, kind, cutoff, order=4):
    """Zero-phase filter applied in the FFT domain -> exactly periodic on a loop buffer."""
    n = x.shape[-1]
    X = np.fft.rfft(x, axis=-1)
    frq = np.fft.rfftfreq(n, 1.0 / SR)
    sos = _sos(kind, cutoff, order)
    _, h = signal.sosfreqz(sos, worN=TAU * frq / SR)
    return np.fft.irfft(X * np.abs(h), n=n, axis=-1)


def peaking(x, f0, gain_db, q=1.0, sr=SR):
    """RBJ peaking EQ."""
    A = 10 ** (gain_db / 40.0)
    w0 = TAU * f0 / sr
    alpha = np.sin(w0) / (2 * q)
    b = [1 + alpha * A, -2 * np.cos(w0), 1 - alpha * A]
    a = [1 + alpha / A, -2 * np.cos(w0), 1 - alpha / A]
    b = np.array(b) / a[0]
    a = np.array(a) / a[0]
    return signal.lfilter(b, a, x, axis=-1)


def resonators(x, freqs, gains_db, q=8.0):
    y = x
    for f, g in zip(freqs, gains_db):
        if abs(g) > 0.01:
            y = peaking(y, f, g, q)
    return y


def noise_morph(n, centers, amps, taus, q=2.2, seed=0, ons=None):
    """Time-varying spectral sweep built from static band-passed noise layers
    with staggered onset/envelopes (click-free alternative to a swept filter)."""
    w = noise(n, seed)
    out = np.zeros(n)
    if ons is None:
        ons = [0.0] * len(centers)
    atk = ns(0.006)
    for i, c in enumerate(centers):
        lo = c / (1 + 1 / (2 * q))
        hi = min(c * (1 + 1 / (2 * q)), SR * 0.47)
        lo = max(lo, 25.0)
        if hi <= lo * 1.05:
            continue
        layer = filt(w, 'bp', (lo, hi), 2)
        o = ns(ons[i])
        e = np.zeros(n)
        m = n - o
        if m > 0:
            e[o:] = np.exp(-np.arange(m) / max(taus[i] * SR, 1.0))
            a = min(atk, m)
            e[o:o + a] *= np.sin(np.linspace(0, np.pi / 2, a)) ** 2
        out += amps[i] * e * layer
    return out


def svf(x, fc, q=1.0, mode='lp'):
    """TPT state-variable filter with per-sample (or scalar) fc; stable at all fc."""
    x = np.asarray(x, dtype=float)
    fc = np.broadcast_to(np.asarray(fc, dtype=float), x.shape)
    g = np.tan(np.pi * np.clip(fc, 20.0, SR * 0.47) / SR)
    k = 1.0 / q
    ic1 = ic2 = 0.0
    out = np.empty_like(x)
    for i in range(x.shape[0]):
        gi = g[i]
        a1 = 1.0 / (1.0 + gi * (gi + k))
        a2 = gi * a1
        a3 = gi * a2
        v3 = x[i] - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2 * v1 - ic1
        ic2 = 2 * v2 - ic2
        out[i] = v2 if mode == 'lp' else (v1 if mode == 'bp' else v3)
    return out


def svf_bp(x, fc, q=2.0):
    return svf(x, fc, q, 'bp')


def svf_lp(x, fc, q=0.9):
    return svf(x, fc, q, 'lp')


# ---------------------------------------------------------------- envelopes
def env_exp(n, tau, atk=0.002, curve=1.0):
    e = np.exp(-((tt(n) / max(tau, 1e-6)) ** curve))
    a = min(ns(atk), max(n - 1, 1))
    if a > 0:
        e[:a] *= np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    return e


def env_adsr(n, a, d, s, r):
    """Attack/decay/sustain-level/release; release occupies the final r seconds of n."""
    na, nd, nr = ns(a), ns(d), ns(r)
    nr = min(nr, n)
    body = n - nr
    e = np.zeros(n)
    na = min(na, max(body, 1))
    e[:na] = np.linspace(0, 1, na) ** 0.8
    nd = min(nd, max(body - na, 0))
    if nd > 0:
        e[na:na + nd] = 1 + (s - 1) * (1 - np.exp(-np.linspace(0, 3, nd))) / (1 - np.exp(-3))
    if body > na + nd:
        e[na + nd:body] = s
    if nr > 0:
        start = e[body - 1] if body > 0 else s
        e[body:] = start * np.exp(-np.linspace(0, 5, nr)) * np.cos(np.linspace(0, np.pi / 2, nr)) ** 0.6
    return e


def env_swell(n, a, r, peak_lvl=1.0):
    """Swell up over a, hold, release over r (r at the end of n)."""
    e = np.zeros(n)
    na, nr = min(ns(a), n), min(ns(r), n)
    e[:na] = np.linspace(0, 1, na) ** 1.3 * peak_lvl
    if nr > 0 and n - nr > na:
        e[na:n - nr] = peak_lvl
        e[n - nr:] = peak_lvl * (np.cos(np.linspace(0, np.pi / 2, nr)) ** 1.6)
    elif na < n:
        e[na:] = peak_lvl * np.exp(-np.linspace(0, 4, n - na))
    return e


def fades(x, fin=0.002, fout=0.005):
    y = np.array(x, dtype=float, copy=True)
    n = y.shape[-1]
    fa, fo = min(ns(fin), n), min(ns(fout), n)
    if fa > 0:
        sl = [slice(None)] * y.ndim
        sl[-1] = slice(0, fa)
        y[tuple(sl)] *= np.sin(np.linspace(0, np.pi / 2, fa)) ** 2
    if fo > 0:
        sl = [slice(None)] * y.ndim
        sl[-1] = slice(n - fo, n)
        y[tuple(sl)] *= np.cos(np.linspace(0, np.pi / 2, fo)) ** 2
    return y


# ---------------------------------------------------------------- reverb
def make_ir(dur=0.8, decay=0.3, lp=8000, hp=180, predelay=0.01, seed=7, er=0.5):
    """Perceptually better noise IR than a single-band exponential:

    * frequency-dependent decay — highs damp fast (decay*0.55), mids at
      `decay`, lows ring on (decay*1.7). Real rooms behave this way and it
      stops reverb tails from sounding like white noise on a fader.
    * early reflections are short *smeared* bursts (1.5 ms), not single
      sample spikes — spikes comb-filter into a metallic ringing.
    * predelay gap, then energy-normalized (rev()'s wet gain stays meaningful).
    """
    n = ns(dur)
    t_ = tt(n)
    w = noise(n, seed)
    lo = filt(w, 'lp', 320, 2)
    mid = filt(w, 'bp', (320, 2600), 2)
    hi = filt(w, 'hp', 2600, 2)
    ir = (lo * np.exp(-t_ / (decay * 1.7))
          + mid * np.exp(-t_ / decay)
          + hi * np.exp(-t_ / (decay * 0.55)))
    ir *= 1.0 - np.exp(-t_ / 0.004)          # 4 ms diffusion build-up
    pd = ns(predelay)
    ir[:pd] = 0.0
    rng = np.random.default_rng(seed + 1)
    smear = ns(0.0015)
    sw = np.hanning(smear) if smear > 1 else np.ones(1)
    t_k = pd
    for k in range(10):                       # densifying early reflections
        t_k += int(rng.uniform(0.003, 0.016) * SR)
        if t_k + smear >= n:
            break
        tap = filt(noise(smear, seed + 10 + k), 'lp',
                   1800 + 3000 * rng.random(), 2) * sw
        ir[t_k:t_k + smear] += er * (0.95 ** k) * rng.uniform(0.5, 1.0) * \
            (-1.0 if rng.random() > 0.5 else 1.0) * tap
    if lp:
        ir = filt(ir, 'lp', lp, 2)
    if hp:
        ir = filt(ir, 'hp', hp, 2)
    e = np.sqrt(np.sum(ir ** 2))
    return ir / (e + 1e-12)


def rev(x, ir, wet=0.3, dry=1.0):
    if x.ndim == 1:
        y = signal.fftconvolve(x, ir, mode='full')[:x.shape[-1]]
    else:
        y = signal.fftconvolve(x, ir[None, :], mode='full', axes=-1)[..., :x.shape[-1]]
    return dry * x + wet * y


def circ_conv(x, ir):
    """Circular convolution -> reverb tails wrap around a loop buffer seamlessly."""
    n = x.shape[-1]
    h = np.zeros(n)
    m = min(len(ir), n)
    h[:m] = ir[:m]
    H = np.fft.rfft(h)
    return np.fft.irfft(np.fft.rfft(x, axis=-1) * H, n=n, axis=-1)


def circ_rev(x, ir, wet=0.3, dry=1.0):
    return dry * x + wet * circ_conv(x, ir)


# ---------------------------------------------------------------- gain / limiting
def soft_ceil(x, ceil):
    return ceil * np.tanh(x / ceil)


def balance(x, target_db, ceil, g_lo=0.005, g_hi=6.0, iters=55):
    """Find linear gain `a` so that soft-limited y = ceil*tanh(a*x/ceil) has the
    requested RMS in dB. Peak of the result never exceeds `ceil`.
    rms(soft_ceil(a*x)) is monotonic in `a`, so a bisection is exact."""
    xn = norm_peak(x)
    if rms_db(soft_ceil(g_hi * xn, ceil)) < target_db:
        return soft_ceil(g_hi * xn, ceil)          # unreachable -> best effort
    if rms_db(soft_ceil(g_lo * xn, ceil)) > target_db:
        return soft_ceil(g_lo * xn, ceil)
    lo, hi = g_lo, g_hi
    for _ in range(iters):
        a = 0.5 * (lo + hi)
        if rms_db(soft_ceil(a * xn, ceil)) < target_db:
            lo = a
        else:
            hi = a
    return soft_ceil(0.5 * (lo + hi) * xn, ceil)


def fix_peak(x, ceil):
    p = peak(x)
    return x if p <= ceil else x * (ceil / p)


def balance_chain(x, target_db, ceil, g_hi=6.0, iters=48, hp=None, fade=None,
                  circular=False):
    """Like balance(), but the gain search runs through the *final* processing
    chain, so the RMS actually measured on the shipped file lands on target:
        gain -> 20 Hz high-pass (DC/subsonic) -> soft limiter -> mean removal
        -> edge fades
    The limiter is last, so the ceiling is guaranteed; DC created by asymmetric
    saturation is removed by mean subtraction (costs no audible energy).
    circular=True uses an FFT-domain high-pass, keeping a music loop exactly
    periodic."""
    xn = norm_peak(x)

    def chain(a):
        y = a * xn
        if hp:
            y = fft_filt(y, 'hp', hp, 2) if circular else filt(y, 'hp', hp, 2)
        y = soft_ceil(y, ceil)
        y = y - np.mean(y, axis=-1, keepdims=True)
        if fade:
            y = fades(y, *fade)
        return y

    if rms_db(chain(g_hi)) < target_db:
        return chain(g_hi)
    if rms_db(chain(1e-4)) > target_db:
        return chain(1e-4)
    lo, hi = 1e-4, g_hi
    for _ in range(iters):
        a = 0.5 * (lo + hi)
        if rms_db(chain(a)) < target_db:
            lo = a
        else:
            hi = a
    return chain(0.5 * (lo + hi))


# ---------------------------------------------------------------- loop rendering
class LoopBuf:
    """Fixed-length buffer; added events wrap around the end so the audio is
    exactly periodic (seamless loop by construction)."""

    def __init__(self, dur, channels=1):
        self.n = ns(dur)
        self.ch = channels
        self.buf = np.zeros((channels, self.n))

    @property
    def t(self):
        return tt(self.n)

    def add(self, tsec, sig, gain=1.0, pan=0.0, width=0.0):
        sig = np.atleast_2d(np.asarray(sig, dtype=float))
        if sig.shape[0] == 1 and self.ch == 2:
            if width > 0:      # slight L/R decorrelation for stereo width
                d = ns(width)
                extra = np.roll(sig, d, axis=-1)
                sig = np.vstack([0.65 * sig + 0.35 * extra,
                                 0.65 * extra + 0.35 * sig])
            elif abs(pan) > 1e-6:
                gl = np.cos((pan + 1) * np.pi / 4)
                gr = np.sin((pan + 1) * np.pi / 4)
                sig = np.vstack([gl * sig, gr * sig])
            else:
                sig = np.vstack([sig, sig])
        elif sig.shape[0] != self.ch:
            raise ValueError('channel mismatch')
        i = ns(tsec) % self.n
        m = sig.shape[-1]
        first = min(m, self.n - i)
        self.buf[:, i:i + first] += sig[:, :first] * gain
        off = first
        while off < m:
            c = min(m - off, self.n)
            self.buf[:, 0:c] += sig[:, off:off + c] * gain
            off += c


# ---------------------------------------------------------------- file IO
def write_wav(path, x, sr=SR):
    import wave
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        x = x[:, None]
    elif x.shape[0] <= 2 and x.shape[0] < x.shape[1]:
        x = x.T
    x = np.ascontiguousarray(x)
    ints = np.round(np.clip(x, -1.0, 1.0) * 8388607.0).astype('<i4', order='C')
    ints = np.ascontiguousarray(ints)
    raw = ints.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    w = wave.open(path, 'wb')
    w.setnchannels(x.shape[1])
    w.setsampwidth(3)
    w.setframerate(sr)
    w.writeframes(raw)
    w.close()
    return path


def ffprobe(path):
    import subprocess, json
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0',
                          '-show_entries', 'stream=codec_name,sample_rate,channels,duration',
                          '-show_entries', 'format=duration', '-of', 'json', path],
                         check=True, capture_output=True, text=True).stdout
    j = json.loads(out)
    st = j['streams'][0]
    return {'codec': st.get('codec_name'), 'sr': int(st.get('sample_rate', 0)),
            'ch': int(st.get('channels', 0)),
            'dur': float(st.get('duration') or j['format']['duration'])}


def read_pcm_f32(path):
    """Decode any audio file to float32 numpy array shaped (n, channels)."""
    import subprocess, tempfile, os
    ch = ffprobe(path)['ch']
    fd, tmp = tempfile.mkstemp(suffix='.raw')
    os.close(fd)
    try:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-f', 'f32le',
                        '-acodec', 'pcm_f32le', tmp], check=True)
        a = np.fromfile(tmp, dtype='<f4')
    finally:
        os.remove(tmp)
    return a.reshape(-1, ch)


def loudnorm_measure(path):
    """Integrated loudness + true peak via ffmpeg loudnorm JSON (printed on stderr)."""
    import subprocess, json, re
    p = subprocess.run(['ffmpeg', '-hide_banner', '-i', path,
                        '-af', 'loudnorm=print_format=json', '-f', 'null', '-'],
                       capture_output=True, text=True)
    txt = p.stdout + p.stderr
    m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', txt, re.S)
    if not m:
        return None
    j = json.loads(m.group(0))
    return {'lufs': float(j['input_i']), 'tp': float(j['input_tp']),
            'lra': float(j.get('input_lra', 0)), 'thresh': float(j.get('input_thresh', 0))}
