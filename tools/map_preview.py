"""Top-down map preview for design review. Run with the venv python."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "emberfall"))
import pygame
from src.mapgen import generate_map, GRASS, DIRT, ROCK, WATER, SAND, ASH, BLOOD, MOSS
from src.defs import BUILDINGS

COL = {
    GRASS: (75, 107, 63), DIRT: (129, 103, 74), ROCK: (102, 98, 92),
    WATER: (38, 92, 104), SAND: (188, 170, 122), ASH: (73, 64, 79),
    BLOOD: (92, 31, 40), MOSS: (56, 82, 49),
}

def main(path="design/map-preview.png", scale=12):
    m = generate_map()
    W = m.w * scale
    pad = 40
    H = m.h * scale + 170
    s = pygame.Surface((W + pad * 2, H), pygame.SRCALPHA)
    s.fill((20, 17, 26))
    for y in range(m.h):
        for x in range(m.w):
            c = COL[m.terr(x, y)]
            # height shading
            hgt = m.height[m.i(x, y)]
            if hgt:
                f = 1.0 + (hgt - 1) * 0.13
                c = tuple(min(255, int(v * f)) for v in c)
            r = pygame.Rect(pad + x * scale, pad + y * scale, scale, scale)
            pygame.draw.rect(s, c, r)
            if m.road[m.i(x, y)]:
                pygame.draw.rect(s, (150, 120, 84), r.inflate(-5, -5))
            if m.ramp[m.i(x, y)]:
                pygame.draw.rect(s, (196, 168, 118), r, 2)
    for p in m.props:
        px = pad + int(p["x"] * scale); py = pad + int(p["y"] * scale)
        if p["kind"] in ("tree", "pine", "dead"):
            pygame.draw.circle(s, (34, 66, 36) if p["kind"] != "dead" else (78, 70, 55), (px, py), 4)
    for mine in m.mines:
        px = pad + int(mine["x"] * scale); py = pad + int(mine["y"] * scale)
        pygame.draw.rect(s, (226, 188, 82), pygame.Rect(px - 8, py - 8, 16, 16))
        pygame.draw.rect(s, (30, 24, 18), pygame.Rect(px - 8, py - 8, 16, 16), 2)
    for side, color, label in ((1, (220, 90, 60), "PLAYER"), (2, (150, 110, 200), "ENEMY")):
        st = m.starts[side]
        for b in st["buildings"]:
            bw, bh = BUILDINGS[b["type"]]["size"]
            r = pygame.Rect(pad + b["x"] * scale, pad + b["y"] * scale, bw * scale, bh * scale)
            pygame.draw.rect(s, (*color, 90), r)
            pygame.draw.rect(s, color, r, 2)
        for u in st["units"]:
            ut, ux, uy = u if isinstance(u, tuple) else (u["type"], u["x"], u["y"])
            pygame.draw.circle(s, color, (pad + int(ux * scale), pad + int(uy * scale)), 3)
        c = st["camera"]
        pygame.draw.circle(s, color, (pad + int(c[0] * scale), pad + int(c[1] * scale)), 7, 2)
    for camp in m.camps:
        cx = pad + int(camp["x"] * scale); cy = pad + int(camp["y"] * scale)
        pygame.draw.line(s, (235, 120, 90), (cx - 6, cy - 6), (cx + 6, cy + 6), 2)
        pygame.draw.line(s, (235, 120, 90), (cx - 6, cy + 6), (cx + 6, cy - 6), 2)
    font = pygame.font.Font(None, 22)
    small = pygame.font.Font(None, 18)
    y0 = pad + m.h * scale + 12
    s.blit(font.render("ASHEN VALE — layout preview", True, (232, 220, 192)), (pad, y0))
    legend = "gold=gold mine  red/blue=starts  X=creep camp  green dots=trees  2px outline=ramp"
    s.blit(small.render(legend, True, (170, 160, 140)), (pad, y0 + 26))
    s.blit(small.render(f"problems: {m.problems or 'none'}  trees:{len(m.wood)}  props:{len(m.props)}", True, (170, 160, 140)), (pad, y0 + 46))
    pygame.image.save(s, path)
    print("saved", path, s.get_size())

if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode((1, 1))
    main()
