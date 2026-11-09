from PIL import Image, ImageDraw, ImageFont
import os, sys

TILED = "/run/media/wyene/disk/project/game/vendor/flare-game/tiled/tilesheets"
OUT = os.path.dirname(os.path.abspath(__file__))

def sheet(name, cols, cw, ch, rows, scale=0.6, chunk=4, gid0=0):
    im = Image.open(os.path.join(TILED, name)).convert("RGBA")
    font = ImageFont.load_default(size=22)
    for c in range(0, rows, chunk):
        r0, r1 = c, min(c + chunk, rows)
        cellw, cellh = int(cw*scale), int(ch*scale)
        lab = 26
        W = cols*(cellw+4)+4
        H = (r1-r0)*(cellh+lab+4)+4
        out = Image.new("RGBA", (W, H), (30, 30, 34, 255))
        d = ImageDraw.Draw(out)
        for r in range(r0, r1):
            for col in range(cols):
                x = 4 + col*(cellw+4); y = 4 + (r-r0)*(cellh+lab+4)
                cell = im.crop((col*cw, r*ch, col*cw+cw, r*ch+ch)).resize((cellw, cellh), Image.LANCZOS)
                d.rectangle([x, y, x+cellw, y+cellh], fill=(70,70,76,255))
                out.alpha_composite(cell, (x, y))
                gid = gid0 + r*cols + col
                d.text((x+2, y+cellh+2), str(gid), font=font, fill=(255,230,120,255))
        p = os.path.join(OUT, "%s_r%d-%d.png" % (name.replace(".png",""), r0, r1-1))
        out.save(p)
        print(p, out.size)

if __name__ == "__main__":
    sheet("grassland.png", 16, 192, 384, 8, scale=0.62, chunk=4)
    sheet("grassland_structures.png", 16, 192, 768, 2, scale=0.5, chunk=2)
    sheet("grassland_2x2.png", 4, 384, 192, 8, scale=0.7, chunk=4)
    sheet("grassland_trees.png", 16, 192, 384, 8, scale=0.62, chunk=4)
    sheet("ruins_2x2.png", 4, 384, 192, 1, scale=0.7, chunk=1)
    sheet("ruins.png", 16, 192, 384, 22, scale=0.62, chunk=4)
