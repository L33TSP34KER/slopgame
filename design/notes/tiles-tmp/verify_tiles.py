"""Quality gates for the EMBERFALL tile sheets."""
import sys, os, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
from tilekit import TW, TH, lum
import build_tiles as B

SHEETS = [("emberfall_ground.png", 8), ("emberfall_edges.png", 8), ("emberfall_water.png", 2)]
CORE = B.F < 0.45
CORN = [(0, 0), (0, TW - 1), (TH - 1, 0), (TH - 1, TW - 1)]
OUT = B.F > 1.30
fail = []

for name, nrows in SHEETS:
    p = os.path.join(B.OUT_DIR, name)
    im = Image.open(p)
    kb = os.path.getsize(p) / 1024
    ok = im.size == (16 * TW, nrows * TH) and im.mode == "RGBA"
    print(f"{name}: {im.size} {im.mode} {kb:.0f} KB  -> {'OK' if ok else 'FAIL'}")
    if not ok: fail.append(f"{name} geometry")
    if kb > 1536: fail.append(f"{name} >1.5MB")
    a = np.asarray(im.convert("RGBA")).astype(np.float64)
    bad_corner = bad_centre = 0
    for r in range(nrows):
        for c in range(16):
            t = a[r*TH:(r+1)*TH, c*TW:(c+1)*TW]
            for (y, x) in CORN:
                if t[y, x, 3] != 0: bad_corner += 1
            if not (t[..., 3][CORE] == 255).all(): bad_centre += 1
            if t[..., 3][OUT].max() != 0: bad_corner += 1
    print(f"   corners/opaque-outside violations={bad_corner}  tiles-with-nonopaque-core={bad_centre}")
    if bad_corner or bad_centre: fail.append(f"{name} alpha")

# per-tile brightness spread + duplicate detection on the ground sheet
a = np.asarray(Image.open(os.path.join(B.OUT_DIR, "emberfall_ground.png"))).astype(np.float64)
names = [g[0] for g in B.GROUND]
print("\nrow            mean-L range (per tile)   gain spread   adjacent pairs identical?")
for r, n in enumerate(names):
    ls, hashes, rgbm = [], [], []
    for c in range(16):
        t = a[r*TH:(r+1)*TH, c*TW:(c+1)*TW]
        ls.append(float(lum(t[..., :3])[CORE].mean()))
        rgbm.append(t[..., :3][CORE].reshape(-1, 3).mean(axis=0))
        hashes.append(hashlib.md5(np.round(t[..., :3], 3).tobytes()).hexdigest()[:8])
    ls = np.array(ls)
    rel = (ls / ls.mean() - 1) * 100
    dup = sum(1 for c in range(15) if hashes[c] == hashes[c+1])
    near = max(float(np.abs(rgbm[c] - rgbm[c+1]).mean()) for c in range(15))
    print(f"{n:12s}  L {ls.min():6.1f}..{ls.max():6.1f}   {rel.min():+5.1f}%..{rel.max():+5.1f}%"
          f"   dup={dup}  min adjacent mean-diff={near:.2f}")
    if dup: fail.append(f"{n} duplicate tiles side by side")
    if abs(rel).max() > 4.6: fail.append(f"{n} brightness out of +-4%")

# no baked background / labels: sheet must be mostly transparent between diamonds
for name, nrows in SHEETS:
    a = np.asarray(Image.open(os.path.join(B.OUT_DIR, name))).astype(np.float64)
    frac = float((a[..., 3] == 0).mean())
    print(f"{name}: transparent fraction {frac:.3f}")
    if frac < 0.35: fail.append(f"{name} looks opaque/backgrounded")

print("\nRESULT:", "ALL GATES PASS" if not fail else "FAIL -> " + "; ".join(fail))
json.dump({"fail": fail}, open("design/notes/tiles-tmp/verify.json", "w"))
