"""EMBERFALL flare tile sheet builder (scratch builder; deliverables are the PNGs + flare-tiles.md).

Geometry contract
-----------------
Tile cell 64x32, diamond centre (32,16), pixel centres at (i+0.5, j+0.5).
  f = |px-32|/32 + |py-16|/16
The diamonds centred on the iso lattice (32+32(c-r), 16+16(c+r)) tile the plane exactly
and, with pixel centres on the half-integers, no pixel centre ever lands on a diamond
edge, so `alpha = 255 for f<=1 else 0` gives full opaque coverage with no translucent
lattice lines (a feather would move the neighbour's alpha>0 frontier inward, to a place
where the rim blend is not finished, which is exactly what produced dark seams).

Every tile's RGB is blended toward a per-row shared reference image over
f = 0.52 -> 0.90 and is EXACTLY that reference for f >= 0.90 (the outer 1.4px, which is
where every inter-tile boundary lives), so two neighbouring tiles carry identical colour
where they meet.  All 8 ground rows sit in a narrow luminance band so that the neutral
mid-point rim used by the edge rows stays within ~6 levels of every pure row.
"""
import sys, os, json, math
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
os.chdir(ROOT)
from tilekit import TW, TH, composite_iso, seam_stats, lum

OUT_DIR = "assets/flare/raw/tiles"
NOTE_DIR = "design/notes"
TMP = "design/notes/tiles-tmp"

# ----------------------------------------------------------------- geometry --
ys, xs = np.mgrid[0:TH, 0:TW]
PX, PY = xs + 0.5, ys + 0.5
F = np.abs(PX - TW / 2) / (TW / 2) + np.abs(PY - TH / 2) / (TH / 2)
INSIDE = F <= 1.0
CORE = F < 0.45
RIM_F0, RIM_F1 = 0.52, 0.90     # blend band; identity (pure ref) for f >= RIM_F1


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


RIM_W = smoothstep((F - RIM_F0) / (RIM_F1 - RIM_F0))
ALPHA = np.where(INSIDE, 255.0, 0.0)


def noise(scale, seed):
    rng = np.random.default_rng(seed)
    g = (rng.random((TH // scale + 3, TW // scale + 3)) * 255).astype(np.uint8)
    im = Image.fromarray(g, "L").resize((TW, TH), Image.BICUBIC)
    return np.asarray(im).astype(np.float64)[:TH, :TW] / 255.0 - 0.5


# ------------------------------------------------------------------ sources --
A = "assets/flare/raw/tiles/"
V = "vendor/flare-game/tiled/tilesheets/"
IDENT = (1.0, 1.0, 1.0)

# name, path, y, src tile w/h, tint.  Target luminance of every row: 72..100.
GROUND = [
    ("grass",     A + "grassland.png",      96,  64,  32, (1.00, 1.00, 1.00)),   # L 81
    ("grass_dry", A + "grassland.png",      96,  64,  32, (1.280, 1.020, 0.860)),  # L 88
    ("dirt",      V + "ruins.png",         2208, 192,  96, (1.78, 1.78, 1.78)),   # L 78
    ("dirt_road", V + "cave.png",           288, 192,  96, (1.51, 1.51, 1.51)),   # L 80
    ("sand",      V + "snowplains.png",     288, 192,  96, (0.531, 0.472, 0.404)),  # L 101
    ("ash",       V + "snowplains.png",     672, 192,  96, (0.457, 0.419, 0.390)),  # L 75.5
    ("stone",     A + "grassland.png",      224,  64,  32, (1.00, 0.98, 1.06)),   # L 83
    ("moss",      V + "grassland.png",      288, 192,  96, (0.94, 1.31, 1.33)),   # L 85
]

EDGE_PAIRS = [
    ("grass__dirt",   "grass",   "dirt"),
    ("grass__sand",   "grass",   "sand"),
    ("grass__ash",    "grass",   "ash"),
    ("grass__stone",  "grass",   "stone"),
    ("dirt__road",    "dirt",    "dirt_road"),
    ("grass__moss",   "grass",   "moss"),
    ("ash__stone",    "ash",     "stone"),
    ("dirt__sand",    "dirt",    "sand"),
]

WATER_BASE = (A + "grassland_water.png", 160, 64, 32)
DEEP = np.array([34.0, 48.0, 58.0])       # L 44
SHALLOW = np.array([96.0, 132.0, 130.0])  # L 121  -> 5.1 levels per step


# ------------------------------------------------------------------ loading --
def load_row(path, y, tw, th, ncols=16, tint=IDENT):
    arr = np.asarray(Image.open(path).convert("RGBA")).astype(np.float64)
    rgbs, wts = [], []
    for c in range(ncols):
        t = arr[y:y + th, c * tw:(c + 1) * tw]
        a01 = t[..., 3] / 255.0
        if (tw, th) != (TW, TH):
            pm = Image.fromarray(np.clip(t[..., :3] * a01[..., None], 0, 255).astype(np.uint8), "RGB")
            am = Image.fromarray(np.clip(a01 * 255, 0, 255).astype(np.uint8), "L")
            pm = np.asarray(pm.resize((TW, TH), Image.LANCZOS)).astype(np.float64)
            a1 = np.asarray(am.resize((TW, TH), Image.LANCZOS)).astype(np.float64) / 255.0
            rgb = np.where(a1[..., None] > 1e-3, pm / np.maximum(a1[..., None], 1e-3), 0.0)
            w = a1
        else:
            rgb, w = t[..., :3].copy(), a01.copy()
        rgb = np.clip(rgb * np.asarray(tint, dtype=np.float64), 0, 255)
        rgbs.append(rgb)
        wts.append(w)
    return np.stack(rgbs), np.stack(wts)


def cblur(img, radius):
    """Circular (wrap-around) box blur x3 ~ gaussian.  Wrapping keeps the result
    exactly periodic with the 64x32 cell, which is what makes the rim reference
    lattice-periodic."""
    out = img.astype(np.float64).copy()
    for _ in range(3):
        acc = out.copy()
        for s in range(1, radius + 1):
            acc += np.roll(out, s, 0) + np.roll(out, -s, 0)
            acc += np.roll(out, s, 1) + np.roll(out, -s, 1)
        out = acc / (1 + 4 * radius)
    return out


def shared_ref(rgbs, wts):
    """Per-pixel weighted mean across the row -> smooth -> phase-averaged over the
    two-element lattice group {(0,0),(32,16)}.

    Two tiles sample their rim reference at screen positions differing by a lattice
    vector; lattice vectors are congruent to (0,0) or (32,16) modulo the 64x32 cell and
    2*(32,16) == one full cell wrap, so
        h(u) = (g(u) + g(u-(32,16))) / 2   =>   h(u) == h(u-(32,16))
    holds exactly.  A lattice-periodic reference gives *identical* rim colour on both
    sides of every tile boundary (seam delta = the reference's own 1px gradient only),
    while still carrying the smooth structure common to the whole row.

    The outer 10% of the source diamond is excluded from the average (LANCZOS ringing
    after the 3:1 downscale makes resampled rim pixels unreliable) and extrapolated
    radially inward from the f=0.90 contour instead."""
    core = (F <= 0.90)
    W = (wts * core[None]).sum(axis=0)
    m = W > 1e-3
    ref = np.where(m[..., None],
                   (rgbs * (wts * core[None])[..., None]).sum(axis=0)
                   / np.maximum(W[..., None], 1e-3), 0.0)
    ref = np.where(m[..., None], ref, rgbs[:, m].reshape(-1, 3).mean(axis=0))
    ext = F > 0.90
    if ext.any():
        scale = np.where(ext, 0.90 / np.maximum(F, 1e-6), 1.0)
        sx = np.clip(np.round(TW / 2 + (PX - TW / 2) * scale).astype(int), 0, TW - 1)
        sy = np.clip(np.round(TH / 2 + (PY - TH / 2) * scale).astype(int), 0, TH - 1)
        ref = np.where(ext[..., None], ref[sy, sx], ref)
    ref = cblur(ref, 3)
    return 0.5 * (ref + np.roll(np.roll(ref, 16, axis=0), 32, axis=1))


def finish(rgb, gain, ref):
    g = np.asarray(gain, dtype=np.float64)
    if g.ndim == 2:
        g = g[..., None]
    out = np.clip(rgb * g, 0, 255) * (1.0 - RIM_W[..., None]) + ref * RIM_W[..., None]
    return np.dstack([np.clip(out, 0, 255), ALPHA])


def gains(n=16, phase=0.0, amp=0.035):
    return 1.0 + amp * np.sin(np.arange(n) * 1.9 + phase)


def blob(seed, scale=5):
    """Smooth +-1 field, used as a subtle per-tile brightness drift so that no two
    tiles of a row read the same.  It is applied before the rim blend, so the shared
    rim reference (and therefore the seam delta) is unaffected."""
    rng = np.random.default_rng(seed)
    g = rng.random((TH // scale + 3, TW // scale + 3))
    im = Image.fromarray((g * 255).astype(np.uint8), "L").resize((TW, TH), Image.BICUBIC)
    a = np.asarray(im).astype(np.float64)[:TH, :TW] / 255.0 - 0.5
    a = a / max(abs(a).max(), 1e-6)
    return a - a[CORE].mean()      # zero-mean over the diamond: leaves per-tile L alone


# -------------------------------------------------------------------- build --
def build_ground():
    rows, refs, metas = {}, {}, {}
    for k, (name, path, y, tw, th, tint) in enumerate(GROUND):
        rgbs, wts = load_row(path, y, tw, th, tint=tint)
        # normalise every source tile to the row's mean luminance so that the ONLY
        # brightness difference between neighbours is the intended +-4% gain
        coreL = lum(rgbs)[:, CORE].mean(axis=1)
        scale = coreL.mean() / coreL
        rgbs = rgbs * scale[:, None, None, None]
        ref = shared_ref(rgbs, wts)
        g = gains(16, phase=k * 0.8)
        rows[name] = [finish(rgbs[i], g[i] * (1.0 + 0.030 * blob(i + 31 * k)), ref)
                      for i in range(16)]
        refs[name] = ref
        L = float(lum(ref[INSIDE]).mean())
        metas[name] = dict(source=path, y=y, src_tile=[tw, th], tint=list(tint),
                           ref_lum=round(L, 1),
                           gain_range=[round(float(g.min()), 4), round(float(g.max()), 4)],
                           spatial_gain=0.030)
        print(f"ground/{name:10s} <- {path} y={y} ({tw}x{th}) refL={L:6.1f}")
    return rows, refs, metas


def split_mask(k, noise_amp=1.6, width=8.0, nseed=1):
    """Interior A/B split for directional variant k (0..7): boundary line rotated from
    near-horizontal to near-vertical, always with negative slope so region A keeps the
    N and W vertices and therefore stays connected to the neutral rim."""
    ang = -(k + 0.5) * math.pi / 8.0
    nx, ny = math.cos(ang), math.sin(ang)
    sd = (PX - TW / 2) * nx + (PY - TH / 2) * ny + noise_amp * noise(7, nseed + k)
    return 1.0 - smoothstep((sd + width / 2) / width)     # 1 = material A


def build_edges(rows, refs):
    out, metas = {}, {}
    for p, (pair, ma, mb) in enumerate(EDGE_PAIRS):
        ta, tb = rows[ma], rows[mb]
        rim = 0.5 * (refs[ma] + refs[mb])          # one neutral rim for the whole row
        tiles = []
        for i in range(16):
            if i < 8:
                m = split_mask(i, noise_amp=1.6, width=8.0, nseed=100 + p * 8)
            else:
                m = split_mask(i - 8, noise_amp=5.5, width=14.0, nseed=500 + p * 8)
            rgb = ta[i][..., :3] * m[..., None] + tb[i][..., :3] * (1.0 - m[..., None])
            gg = (1.0 + 0.03 * math.sin(i * 2.3 + p)) * (1.0 + 0.025 * blob(i + 7 * p + 900))
            tiles.append(finish(rgb, gg, rim))
        out[pair] = tiles
        metas[pair] = dict(a=ma, b=mb,
                           rim_lum=round(float(lum(rim[INSIDE]).mean()), 1),
                           lum_a=round(float(lum(refs[ma][INSIDE]).mean()), 1),
                           lum_b=round(float(lum(refs[mb][INSIDE]).mean()), 1),
                           rim_delta=round(abs(float(lum(rim[INSIDE].mean(axis=0)))
                                               - 0), 1))
        print(f"edges/{pair:14s} A={ma:10s} B={mb:10s} rimL={metas[pair]['rim_lum']}")
    return out, metas


def build_water(rows, refs):
    path, y, tw, th = WATER_BASE
    rgbs, wts = load_row(path, y, tw, th)
    base_mean = rgbs.reshape(16, -1, 3).mean(axis=(1, 2))
    base_ref = shared_ref(rgbs, wts)
    global_base = base_ref[INSIDE].mean(axis=0)
    g = gains(16, phase=2.1, amp=0.015)
    depth, row0 = [], []
    for i in range(16):
        target = DEEP + (SHALLOW - DEEP) * (i / 15.0)
        row0.append(finish(rgbs[i] + (target - base_mean[i]), g[i],
                           base_ref + (target - global_base)))
        depth.append([round(float(v), 1) for v in target])
    shore_rim = 0.5 * (base_ref + refs["sand"])
    row1 = []
    for i in range(16):
        land = rows["sand"][i][..., :3]
        water = row0[min(15, 4 + (i % 8))][..., :3]
        m = (split_mask(i, 1.4, 8.0, 900) if i < 8
             else split_mask(i - 8, 5.0, 14.0, 950))
        rgb = water * m[..., None] + land * (1.0 - m[..., None])
        row1.append(finish(rgb, 1.0 + 0.02 * math.sin(i * 2.7), shore_rim))
    step = float(lum(np.array([SHALLOW - DEEP]))[0]) / 15.0
    meta = dict(source=path, y=y, depth=depth, step_lum=round(step, 2),
                shore_rim_lum=round(float(lum(shore_rim[INSIDE]).mean()), 1))
    return [row0, row1], meta


def sheet(tiles_rows):
    img = np.zeros((len(tiles_rows) * TH, 16 * TW, 4))
    for r, tiles in enumerate(tiles_rows):
        for c, t in enumerate(tiles):
            img[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW] = t
    return img


def save(arr, path):
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA").save(path)
    print(f"  wrote {path}  {os.path.getsize(path)/1024:.0f} KB")


# ------------------------------------------------------------------- patches --
def patch_grid(tiles, n=6, mode="cycle"):
    if mode == "cycle":
        return [[tiles[(r * n + c) % len(tiles)] for c in range(n)] for r in range(n)]
    if mode == "cheb":        # every 8-neighbour differs by <= 1 index (gradients)
        return [[tiles[max(r, c) % len(tiles)] for c in range(n)] for r in range(n)]
    raise ValueError(mode)


def seam_of(canvas, ids, edge=4):
    mx, mean, cnt = seam_stats(canvas, ids, edge=edge)
    return dict(max=round(float(mx), 2), mean=round(float(mean), 2), n=int(cnt))


def coverage(canvas, edge=8):
    """holes = pixels that sit well inside the patch (>= edge px from the union-of-cells
    boundary) yet are not fully opaque."""
    a = canvas[..., 3]
    cell = (a > 0).astype(np.float64)
    k = np.ones((3, 3))
    # cheap separable erosion
    e = cell.copy()
    for _ in range(edge):
        e = np.minimum.reduce([e, np.roll(e, 1, 0), np.roll(e, -1, 0),
                               np.roll(e, 1, 1), np.roll(e, -1, 1)])
    inner = e > 0.5
    hole = inner & (a < 250)
    return int(hole.sum()), float(a[inner].min()) if inner.any() else 255.0


def measure(tiles, mode="cycle", n=6, edge=4):
    grid = patch_grid(tiles, n, mode)
    canvas, ids = composite_iso(grid)
    st = seam_of(canvas, ids, edge)
    holes, mina = coverage(canvas, edge=6)
    st.update(gap_px=holes, min_alpha=round(mina, 1))
    return st, canvas, ids


def straightness(canvas, ids):
    """Line test: compare the mean pixel-to-pixel luminance step ON tile boundaries
    (seam_mean) against the mean step everywhere else (painted texture).  A hard cut
    would make the boundary value the *largest* number in the image."""
    L = lum(canvas[..., :3])
    a = canvas[..., 3]
    k = (a[:-1, 1:] > 250) & (a[:-1, :-1] > 250)
    g = np.abs(L[:-1, 1:] - L[:-1, :-1])
    col = np.array([g[:, j][k[:, j]].mean() if k[:, j].any() else np.nan
                    for j in range(g.shape[1])])
    fin = col[~np.isnan(col)]
    same = k & (ids[:-1, 1:] == ids[:-1, :-1])
    diff = k & (ids[:-1, 1:] != ids[:-1, :-1])
    return dict(max_col=round(float(np.nanmax(col)), 2),
                median_col=round(float(np.median(fin)), 2),
                ratio=round(float(np.nanmax(col) / max(np.median(fin), 1e-6)), 2),
                p95_col=round(float(np.percentile(fin, 95)), 2),
                interior_step=round(float(g[same].mean()), 2),
                boundary_step=round(float(g[diff].mean()), 2),
                boundary_p95=round(float(np.percentile(g[diff], 95)), 2))


# --------------------------------------------------------------------- main --
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rows, refs, gmeta = build_ground()
    save(sheet([rows[n] for n, *_ in GROUND]), f"{OUT_DIR}/emberfall_ground.png")
    edges, emeta = build_edges(rows, refs)
    save(sheet([edges[p] for p, *_ in EDGE_PAIRS]), f"{OUT_DIR}/emberfall_edges.png")
    water_rows, wmeta = build_water(rows, refs)
    save(sheet(water_rows), f"{OUT_DIR}/emberfall_water.png")

    report = {"ground": {}, "edges": {}, "water": {}}
    for name, *_ in GROUND:
        st, cv, _ = measure(rows[name], mode="cycle")
        report["ground"][name] = st
        if name in ("grass", "dirt", "stone"):
            Image.fromarray(np.clip(cv, 0, 255).astype(np.uint8)).save(
                f"{NOTE_DIR}/tiles-patch-{name}.png")
        print(f"  patch/{name:10s} seam max={st['max']:6.2f} mean={st['mean']:5.2f} "
              f"holes={st['gap_px']}")
    for pair, *_ in EDGE_PAIRS:
        st, cv, _ = measure(edges[pair], mode="cycle")
        report["edges"][pair] = st
        if pair == "grass__dirt":
            Image.fromarray(np.clip(cv, 0, 255).astype(np.uint8)).save(
                f"{NOTE_DIR}/tiles-patch-edges.png")
        print(f"  patch/edge:{pair:14s} seam max={st['max']:6.2f} mean={st['mean']:5.2f} "
              f"holes={st['gap_px']}")
    st, cv, _ = measure(water_rows[0], mode="cheb")
    report["water"]["deep_shallow"] = st
    Image.fromarray(np.clip(cv, 0, 255).astype(np.uint8)).save(
        f"{NOTE_DIR}/tiles-patch-water.png")
    print(f"  patch/water depth   seam max={st['max']:6.2f} mean={st['mean']:5.2f} "
          f"holes={st['gap_px']}")
    st, cv, _ = measure(water_rows[1], mode="cycle")
    report["water"]["shore"] = st
    print(f"  patch/water shore   seam max={st['max']:6.2f} mean={st['mean']:5.2f} "
          f"holes={st['gap_px']}")

    # transition strip: grass -> dirt -> stone
    strip = []
    for r in range(6):
        line = []
        for c in range(14):
            if c < 5:
                line.append(rows["grass"][(r * 3 + c) % 16])
            elif c == 5:
                line.append(edges["grass__dirt"][(r * 2) % 16])
            elif c < 10:
                line.append(rows["dirt"][(r * 5 + c) % 16])
            elif c == 10:
                line.append(edges["ash__stone"][(r * 2 + 1) % 16])
            else:
                line.append(rows["stone"][(r * 7 + c) % 16])
        strip.append(line)
    sc, sids = composite_iso(strip)
    Image.fromarray(np.clip(sc, 0, 255).astype(np.uint8)).save(
        f"{NOTE_DIR}/tiles-transition.png")
    st_line = straightness(sc, sids)
    sm = seam_of(sc, sids, edge=6)
    holes, mina = coverage(sc, edge=8)
    report["transition"] = dict(st_line, **{"seam_max": sm["max"], "seam_mean": sm["mean"],
                                "gap_px": holes, "min_alpha": round(mina, 1),
                                "size": list(sc.shape[:2])})
    report["_meta"] = {"ground": gmeta, "edges": emeta, "water": wmeta}
    json.dump(report, open(f"{TMP}/report.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "_meta"}, indent=1))


if __name__ == "__main__":
    main()
