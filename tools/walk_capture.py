import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game,parse_args
from src.defs import PLAYER
g=Game(parse_args(["--qa","--scene","base"])); w=g.world
units=[]
for i,k in enumerate(("footman","knight","archer","hero","worker")):
    u=w.spawn_unit(k,22+i*1.6,72,PLAYER); u.order=None; units.append(u)
w.cmd_move(units,32,72)
frames=[]
for n in range(24):
    for z in range(3): g.update(1/30)
    g.draw()
    # crop around the group
    canvas=g.screen
    frames.append(canvas.copy())
S=pygame.Surface((320*4,240*6));S.fill((26,26,32))
for i in range(24):
    im=frames[i]
    crop=im.subsurface(pygame.Rect(760,380,320,240)).copy()
    S.blit(crop,((i%4)*320,(i//4)*240))
pygame.image.save(S,'design/walk-strip.png');print('saved')
