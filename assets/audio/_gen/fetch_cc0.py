#!/usr/bin/env python3
"""Fetch + convert the CC0 layer samples that gen_sfx.py mixes under its own
synthesis. Hard rule from design/ASSET-CONTRACT.md: "No copyrighted samples" —
so only files explicitly released CC0 / public domain are used.

Sources (all Kenney, all CC0 1.0 — License.txt ships inside each zip and is
copied to cc0/LICENSE-kenney.txt by this script):

  Impact Sounds   https://kenney.nl/assets/impact-sounds     CC0
  RPG Audio       https://kenney.nl/assets/rpg-audio          CC0
  Interface SFX   https://kenney.nl/assets/interface-sounds   CC0 (not used yet)

Kenney has no plain <a href=zip> — the page JS calls
GET https://kenney.nl/download-link/<base64-id> with same-origin Referer and
gets back a signed URL; this script does exactly that (no account, no JS).

    python3 assets/audio/_gen/fetch_cc0.py                 # download + convert
    python3 assets/audio/_gen/fetch_cc0.py --zip-dir DIR   # reuse local zips

Output: assets/audio/_gen/cc0/<name>.wav — 44.1 kHz mono 16-bit, DC removed,
silence-trimmed at the head, peak normalized to -6 dBFS (so the layer gains
written in gen_sfx.py mean the same thing for every file).
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'cc0')
SR = 44100

PACKS = {
    # key -> (page url, download-link id, local zip filename)
    'impact': ('https://kenney.nl/assets/impact-sounds', 'impact-sounds',
               'kenney_impact.zip'),
    'rpg': ('https://kenney.nl/assets/rpg-audio', 'rpg-audio',
            'kenney_rpg-audio.zip'),
}

# pack, path inside zip, output name (what gen_sfx.py loads)
SELECTIONS = [
    ('impact', 'Audio/impactMetal_medium_000.ogg', 'sword-metal'),   # sword clang
    ('rpg', 'Audio/knifeSlice.ogg', 'knife-swipe'),                  # blade whoosh
    ('rpg', 'Audio/chop.ogg', 'axe-chop'),                           # axe in wood
    ('impact', 'Audio/impactWood_light_002.ogg', 'wood-light'),      # hammer tap
    ('impact', 'Audio/impactWood_heavy_000.ogg', 'wood-heavy'),      # body thud
    ('rpg', 'Audio/handleCoins.ogg', 'coins'),                       # coin jingle
    ('impact', 'Audio/impactSoft_heavy_000.ogg', 'body-fall'),       # body fall
    ('rpg', 'Audio/dropLeather.ogg', 'leather'),                     # armour/flesh
    ('impact', 'Audio/impactBell_heavy_002.ogg', 'bell'),            # warm bell
    ('rpg', 'Audio/cloth1.ogg', 'cloth'),                            # parchment
    ('impact', 'Audio/impactTin_medium_001.ogg', 'tin-ring'),        # muted metal
    ('impact', 'Audio/impactGeneric_light_002.ogg', 'tick'),         # UI tick
]


def signed_url(page_url, asset_id):
    """What the kenney.nl page JS does: GET /download-link/<id> with referer.
    (The data-download-id on the page is the asset path hex-encoded.)"""
    req = urllib.request.Request(
        'https://kenney.nl/download-link/' + asset_id,
        headers={'User-Agent': 'Mozilla/5.0', 'Referer': page_url,
                 'Origin': 'https://kenney.nl', 'X-Requested-With': 'XMLHttpRequest'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())['url']


def download_pack(key, dest):
    page_url, asset_id_path, _ = PACKS[key]
    asset_id = base64.b64encode(asset_id_path.encode()).decode()
    url = signed_url(page_url, asset_id)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                               'Referer': page_url})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, 'wb') as fh:
        fh.write(r.read())
    print(f'downloaded {key}: {os.path.getsize(dest)} bytes')


def decode(path):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1',
                        '-ar', str(SR), '-f', 'f32le', '-'],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype='<f4').astype(np.float64)


def prepare(x):
    """DC remove -> drop leading near-silence -> peak -6 dBFS -> 1 ms fades."""
    x = x - np.mean(x)
    p = np.max(np.abs(x)) + 1e-12
    nz = np.nonzero(np.abs(x) >= 0.01 * p)[0]
    if len(nz):
        x = x[nz[0]:]
    x = x * (0.5 / (np.max(np.abs(x)) + 1e-12))
    f = min(int(0.001 * SR), len(x))
    if f > 1:
        x[:f] *= np.sin(np.linspace(0, np.pi / 2, f)) ** 2
        x[-f:] *= np.cos(np.linspace(0, np.pi / 2, f)) ** 2
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip-dir', default=None,
                    help='directory holding kenney_impact.zip / kenney_rpg-audio.zip')
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    zips = {}
    with tempfile.TemporaryDirectory(prefix='cc0_') as tmp:
        for key, (page_url, asset_id, zname) in PACKS.items():
            z = os.path.join(args.zip_dir or tmp, zname)
            if not os.path.exists(z):
                download_pack(key, z)
            zips[key] = z
        # license text for the repo
        with zipfile.ZipFile(zips['impact']) as zf:
            for n in zf.namelist():
                if n.lower().endswith('license.txt'):
                    open(os.path.join(OUT, 'LICENSE-kenney.txt'), 'wb').write(zf.read(n))
                    break
        for key, rel, name in SELECTIONS:
            with zipfile.ZipFile(zips[key]) as zf:
                data = zf.read(rel)
            src = os.path.join(tmp, os.path.basename(rel))
            open(src, 'wb').write(data)
            x = prepare(decode(src))
            import wave
            w = wave.open(os.path.join(OUT, name + '.wav'), 'wb')
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())
            w.close()
            print(f'{name:12s} {len(x)/SR:.3f}s from {key}:{rel}')
    print('OK ->', OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
