"""Shared helpers for EMBERFALL flare tile sheet work (scratch, not a deliverable)."""
import numpy as np
from PIL import Image

TW, TH = 64, 32


def load(path):
    return np.asarray(Image.open(path).convert('RGBA')).astype(np.float64)


def save(arr, path):
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), 'RGBA').save(path)


def crop(sheet, col, row, tw=TW, th=TH, ox=0, oy=0):
    """Return tile at (col,row) of a sheet, resampled to 64x32 if needed."""
    x = ox + col * tw
    y = oy + row * th
    im = sheet[y:y + th, x:x + tw]
    if im.shape[0] != TH or im.shape[1] != TW:
        pil = Image.fromarray(np.clip(im, 0, 255).astype(np.uint8), 'RGBA')
        pil = pil.resize((TW, TH), Image.LANCZOS)
        im = np.asarray(pil).astype(np.float64)
    return im.copy()


def diamond_field():
    ys, xs = np.mgrid[0:TH, 0:TW]
    return np.abs(xs - (TW - 1) / 2) / (TW / 2) + np.abs(ys - (TH - 1) / 2) / (TH / 2)


def diamond_alpha(f, soft=0.06):
    """Antialiased diamond mask: 1 well inside, 0 outside, linear ramp of width `soft`."""
    return np.clip((1.0 + soft - f) / soft, 0.0, 1.0)


DF = diamond_field()
BASE_MASK = diamond_alpha(DF)


def apply_mask(tile, mask=None):
    out = tile.copy()
    m = BASE_MASK if mask is None else mask
    out[..., 3] = np.minimum(out[..., 3], m * 255.0)
    return out


def lum(rgb):
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def composite_iso(tiles2d, bg=(128, 128, 128)):
    """tiles2d: grid[r][c] of 64x32 RGBA. Iso layout: +1 col -> (+32,+16), +1 row -> (-32,+16)."""
    rows = len(tiles2d)
    cols = len(tiles2d[0])
    W = TW + (cols + rows - 2) * (TW // 2)
    H = TH + (cols + rows - 2) * (TH // 2)
    xoff = (rows - 1) * (TW // 2)
    canvas = np.zeros((H, W, 4))
    canvas[..., :3] = bg
    ids = np.full((H, W), -1, dtype=np.int32)
    tid = 0
    for r in range(rows):
        for c in range(cols):
            x = xoff + (c - r) * (TW // 2)
            y = (c + r) * (TH // 2)
            t = tiles2d[r][c]
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(W, x + TW), min(H, y + TH)
            if x1 <= x0 or y1 <= y0:
                continue
            tx0, ty0 = x0 - x, y0 - y
            tt = t[ty0:ty0 + (y1 - y0), tx0:tx0 + (x1 - x0)]
            a = tt[..., 3:4] / 255.0
            sub = canvas[y0:y1, x0:x1]
            sub[..., :3] = tt[..., :3] * a + sub[..., :3] * (1 - a)
            sub[..., 3:4] = a * 255.0 + sub[..., 3:4] * (1 - a)
            ids[y0:y1, x0:x1] = np.where(tt[..., 3] > 0, tid, ids[y0:y1, x0:x1])
            tid += 1
    return canvas, ids


def seam_stats(canvas, ids, edge=4):
    """Max/mean |delta lum| over 8-neighbour pixel pairs that sit in different tiles
    and are at least `edge` px inside the canvas."""
    rgb = canvas[..., :3]
    L = lum(rgb)
    a = canvas[..., 3]
    H, W = L.shape
    maxd, sumd, n = 0.0, 0.0, 0
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        A = L[max(0, -dy):H - max(0, dy), max(0, -dx):W - max(0, dx)]
        B = L[max(0, dy):H - max(0, -dy), max(0, dx):W - max(0, -dx)]
        IA = ids[max(0, -dy):H - max(0, dy), max(0, -dx):W - max(0, dx)]
        IB = ids[max(0, dy):H - max(0, -dy), max(0, dx):W - max(0, -dx)]
        AA = a[max(0, -dy):H - max(0, dy), max(0, -dx):W - max(0, dx)]
        AB = a[max(0, dy):H - max(0, -dy), max(0, dx):W - max(0, -dx)]
        cross = (IA != IB) & (AA >= 250) & (AB >= 250)
        # drop the outer frame of the block (not an internal boundary)
        ch, cw = cross.shape
        yy, xx = np.mgrid[0:ch, 0:cw]
        yy = yy + max(0, -dy)
        xx = xx + max(0, -dx)
        keep = (yy >= edge) & (yy < H - edge) & (xx >= edge) & (xx < W - edge)
        m = cross & keep
        if m.any():
            d = np.abs(A - B)[m]
            maxd = max(maxd, d.max())
            sumd += d.sum(); n += d.size
    return maxd, (sumd / n if n else 0.0), n


def gap_stats(canvas, edge=6):
    """Return (n_gap_pixels, min_alpha_inside) - translucency in the block interior."""
    a = canvas[..., 3]
    inner = a[edge:-edge, edge:-edge]
    return int((inner < 250).sum()), float(inner.min())


def block(tiles, n=6):
    """Repeat a 16-tile row across an nxn iso block (row-major cycling)."""
    flat = tiles
    return [[flat[(r * n + c) % len(flat)] for c in range(n)] for r in range(n)]
