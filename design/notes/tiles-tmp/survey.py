"""Survey 64x32 rows in source atlases; emit labeled contact sheets + scores."""
import sys, os, json, glob
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tilekit import TW, TH, DF, diamond_alpha, lum

SRC = sorted(set(glob.glob('assets/flare/raw/tiles/*.png')) |
             set(glob.glob('vendor/flare-game/tiled/tilesheets/*.png')))

CORE = DF < 0.86      # well inside diamond
OUTER = DF > 1.18     # corners

def row_score(a):
    """a: (n, TH, TW, 4) float tiles of one row. Return dict."""
    al = a[..., 3]
    cov = al[:, CORE].mean(axis=1)          # interior coverage per tile
    outc = al[:, OUTER].mean(axis=1)        # corner coverage per tile
    L = lum(a[..., :3])
    ctr = L[:, CORE]
    sd = ctr.std(axis=1)                    # texture variance (0 = flat fill)
    # duplicate detection: pairwise mean abs diff of interior rgb
    rgb = a[..., :3][:, CORE]
    n = len(a)
    dup = 0
    mind = 999.0
    for i in range(n):
        for j in range(i+1, n):
            d = np.abs(rgb[i]-rgb[j]).mean()
            mind = min(mind, d)
            if d < 1.5: dup += 1
    rgbm = a[..., :3][:, CORE].mean(axis=1)
    return dict(
        mean_rgb=[float(v) for v in rgbm.mean(axis=0)],
        cov_min=float(cov.min()/255.0), cov_mean=float(cov.mean()/255.0),
        out_max=float(outc.max()/255.0),
        sd_mean=float(sd.mean()), sd_min=float(sd.min()),
        dup_pairs=int(dup), min_pair_diff=float(mind),
        lum_mean=float(ctr.mean()),
    )

def clean_row(s):
    return (s['cov_min'] > 0.985 and s['out_max'] < 0.02
            and s['sd_mean'] > 3.0)

rows = []
for p in SRC:
    im = Image.open(p).convert('RGBA')
    W, H = im.size
    arr = np.asarray(im).astype(np.float64)
    if W % TW or H % TH:
        continue
    for ry in range(H // TH):
        band = arr[ry*TH:(ry+1)*TH]
        best = None
        for ox in (0, 32):
            rolled = np.roll(band, -ox, axis=1)
            tiles = np.stack([rolled[:, cx*TW:(cx+1)*TW] for cx in range(W//TW)])
            s = row_score(tiles)
            if best is None or (s['cov_min'], s['sd_mean']) > (best[0]['cov_min'], best[0]['sd_mean']):
                best = (s, ox)
        s, ox = best
        s.update(path=p, y=ry*TH, ncols=W//TW, ox=ox, keep=clean_row(s))
        rows.append(s)

keep = [r for r in rows if r['keep']]
print(f"total rows {len(rows)}  clean {len(keep)}")
for r in keep:
    print(f"{r['path']:56s} y={r['y']:5d} ox={r['ox']:2d} cov={r['cov_min']:.4f} out={r['out_max']:.4f} "
          f"sd={r['sd_mean']:5.2f} dup={r['dup_pairs']:3d} pdiff={r['min_pair_diff']:5.2f} L={r['lum_mean']:5.1f}")
json.dump(keep, open('design/notes/tiles-tmp/survey_keep.json','w'), indent=1)
