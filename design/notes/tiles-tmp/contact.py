"""Labeled contact sheet of atlas rows (scratch helper)."""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw

BG = (40, 44, 60, 255)
LBL = 76

def sheet(path, out, rows=None, y0=0, y1=None, cols=None, zoom=1):
    im = Image.open(path).convert('RGBA')
    W, H = im.size
    y1 = H if y1 is None else y1
    rows = rows if rows is not None else list(range(y0, y1, 32))
    arr = np.asarray(im).astype(np.float64)
    rh = 32
    canvas = Image.new('RGBA', (W + LBL, len(rows) * rh * zoom), BG)
    d = ImageDraw.Draw(canvas)
    for i, ry in enumerate(rows):
        band = im.crop((0, ry, W, min(H, ry + rh)))
        if zoom != 1:
            band = band.resize((W * zoom, rh * zoom), Image.NEAREST)
        canvas.alpha_composite(band, (LBL, i * rh * zoom))
        d.text((3, i * rh * zoom + 3), f"y={ry}", fill=(255, 230, 120, 255))
        d.line([(0, i * rh * zoom), (W + LBL, i * rh * zoom)], fill=(200, 40, 40, 255))
        for cx in range(0, W + 1, 64):
            d.line([(LBL + cx * zoom, i * rh * zoom), (LBL + cx * zoom, (i + 1) * rh * zoom)],
                   fill=(200, 40, 40, 90))
    canvas.save(out)
    print(out, canvas.size)

if __name__ == '__main__':
    p = sys.argv[1]; out = sys.argv[2]
    y0 = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    y1 = int(sys.argv[4]) if len(sys.argv) > 4 else None
    z = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    sheet(p, out, y0=y0, y1=y1, zoom=z)
