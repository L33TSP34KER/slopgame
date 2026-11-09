import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy"); os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame
pygame.init(); pygame.display.set_mode((1, 1))
from src.art import Art, PARCH, GOLD
from src.defs import UNITS, BUILDINGS, PLAYER, ENEMY, NEUTRAL

art = Art()
units = ["worker","footman","archer","knight","priest","ballista","hero","ghoul","fiend","necromancer","abomination","revenant","skeleton","goblin","goblin-brute","hollow-king"]
teams = {u: (ENEMY if UNITS[u].get("enemy") else NEUTRAL if UNITS[u].get("neutral") else PLAYER) for u in units}
cols, cw, ch = 8, 170, 190
rows = (len(units) + cols - 1) // cols
S = pygame.Surface((cols * cw, rows * ch + 40), pygame.SRCALPHA)
S.fill((22, 20, 26))
for i, u in enumerate(units):
    x = (i % cols) * cw; y = (i // cols) * ch + 20
    pygame.draw.rect(S, (32, 29, 34), (x + 6, y, cw - 12, ch - 8))
    im, ax, ay = art.unit(UNITS[u]["rig"], 0, "idle", 0, teams[u])
    sc = 2.4
    im2 = pygame.transform.smoothscale(im, (int(im.get_width() * sc), int(im.get_height() * sc)))
    S.blit(im2, (x + cw // 2 - im2.get_width() // 2, y + ch - 40 - im2.get_height()))
    f = art.font(16, "serif")
    lab = f.render(u, True, PARCH)
    S.blit(lab, (x + cw // 2 - lab.get_width() // 2, y + ch - 30))
pygame.image.save(S, "design/unit-sheet.png")
print("units sheet", S.get_size())

bids = ["townhall","keep","farm","barracks","mill","blacksmith","sanctum","tower","altar","necropolis","ziggurat","crypt","slaughterhouse","temple","bonetower","altarhollow"]
cols, cw, ch = 4, 330, 300
rows = (len(bids) + cols - 1) // cols
S = pygame.Surface((cols * cw, rows * ch + 30), pygame.SRCALPHA)
S.fill((22, 20, 26))
for i, b in enumerate(bids):
    x = (i % cols) * cw; y = (i // cols) * ch + 10
    pygame.draw.rect(S, (34, 32, 30), (x + 8, y, cw - 16, ch - 10))
    team = ENEMY if BUILDINGS[b].get("enemy") else PLAYER
    im, ax, ay = art.building(b, team, 4)
    S.blit(im, (x + cw // 2 - ax, y + ch - 50 - ay))
    f = art.font(17, "serif"); lab = f.render(b, True, PARCH)
    S.blit(lab, (x + cw // 2 - lab.get_width() // 2, y + ch - 32))
pygame.image.save(S, "design/building-sheet.png")
print("building sheet", S.get_size())
