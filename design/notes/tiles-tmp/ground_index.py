"""Find full rows of ground diamonds in all atlases at 1x and 2x grids."""
import sys, os, glob, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw
from tilekit import lum

def field(th, tw):
    ys, xs = np.mgrid[0:th, 0:tw]
    return np.abs(xs-(tw-1)/2)/(tw/2)+np.abs(ys-(th-1)/2)/(th/2)

BG = (40, 44, 60, 255)
LBL = 84

def main():
    SRC = sorted(set(glob.glob('assets/flare/raw/tiles/*.png')) |
                 set(glob.glob('vendor/flare-game/tiled/tilesheets/*.png')))
    keep = []
    for p in SRC:
        im = Image.open(p).convert('RGBA'); W, H = im.size
        arr = np.asarray(im).astype(np.float64)
        for (tw, th, scale) in ((64, 32, 1), (192, 96, 3), (128, 64, 2)):
            if W % tw or H % th:
                continue
            F = field(th, tw)
            core = F < 0.86
            outer = F > 1.25
            for ox in (0, tw // 2):
                for oy in (0, th // 2):
                    for y in range(oy, H - th + 1, th):
                        xs = list(range(ox % tw, W - tw + 1, tw))
                        if len(xs) < 8:
                            continue
                        T = np.stack([arr[y:y+th, x:x+tw] for x in xs])
                        al = T[..., 3]
                        cov = al[:, core].mean() / 255.0
                        out = al[:, outer].mean() / 255.0
                        sd = lum(T[..., :3])[:, core].std()
                        if cov > 0.85 and out < 0.12 and sd > 3.0:
                            rgb = T[..., :3][:, core].reshape(len(T), -1)
                            pd = float(np.abs(rgb[1:] - rgb[:-1]).mean()) if len(T) > 1 else 99
                            keep.append(dict(path=p, y=y, ox=ox, oy=oy, tw=tw, th=th,
                                             scale=scale, nc=len(xs), cov=float(cov),
                                             out=float(out), sd=float(sd), pd=pd,
                                             mean=[float(v) for v in T[..., :3][:, core].reshape(-1, 3).mean(axis=0)]))
    json.dump(keep, open('design/notes/tiles-tmp/ground_rows.json', 'w'), indent=1)
    print(f"kept {len(keep)} rows")
    # contact sheets: one per atlas+scale
    from collections import defaultdict
    grp = defaultdict(list)
    for k in keep:
        grp[(k['path'], k['scale'])].append(k)
    for (path, scale), items in sorted(grp.items()):
        items.sort(key=lambda k: k['y'])
        base = os.path.basename(path)[:-4]
        out = f"design/notes/tiles-tmp/G_{base}_{scale}x.png"
        cw = 1024
        canvas = Image.new('RGBA', (cw + LBL, len(items) * 32 * scale), BG)
        d = ImageDraw.Draw(canvas)
        for i, k in enumerate(items):
            tw_ = k['tw']
            W0 = Image.open(k['path']).size[0]
            band = Image.open(k['path']).convert('RGBA').crop((0, k['y'], W0, k['y'] + k['th']))
            band = band.resize((band.size[0] * 64 // tw_, 32), Image.LANCZOS)
            canvas.alpha_composite(band, (LBL, i * 32))
            d.text((3, i * 32 + 4), f"y={k['y']} o={k['ox']},{k['oy']}", fill=(255, 230, 120, 255))
            d.line([(0, i * 32), (cw + LBL, i * 32)], fill=(200, 40, 40, 255))
        canvas.save(out)
        print(" ", out, canvas.size, len(items), "rows")

main()
