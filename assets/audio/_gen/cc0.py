"""Loader for the CC0 layer material in assets/audio/_gen/cc0/.

Everything here is Kenney.nl audio released under CC0 1.0 (license text in
cc0/LICENSE-kenney.txt, provenance in fetch_cc0.py). The layers are 44.1 kHz
mono 16-bit WAVs, DC-clean, silence-trimmed, peak-normalized to -6 dBFS, so a
gain of 1.0 in gen_sfx.py means the same loudness for every layer.

gen_sfx.py always keeps its own synthesis underneath — the layers only add the
real-world detail synthesis cannot fake (metal clang, coin jingle, axe bite).
"""
import os
import wave

import numpy as np

CC0_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cc0')
_cache = {}


def load(name, gain=1.0, start=0.0):
    """Return float64 mono samples of layer `name`, optionally starting
    `start` seconds in (to skip a soft lead-in and land the transient)."""
    key = (name, round(start, 4))
    if key in _cache:
        return _cache[key] * gain
    path = os.path.join(CC0_DIR, name + '.wav')
    with wave.open(path, 'rb') as w:
        assert w.getframerate() == 44100 and w.getnchannels() == 1, path
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype='<i2').astype(np.float64) / 32768.0
    if start > 0:
        x = x[int(start * 44100):]
    _cache[key] = x
    return x * gain
