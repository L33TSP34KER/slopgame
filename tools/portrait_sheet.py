import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
pygame.init();pygame.display.set_mode((64,64))
from src.art import Art
from src.defs import PLAYER,ENEMY
a=Art(); rigs=["worker","footman","archer","knight","priest","hero","ghoul","fiend","necromancer","abomination"]
S=pygame.Surface((len(rigs)*170,220));S.fill((40,38,44))
f=pygame.font.Font(None,20)
for i,r in enumerate(rigs):
    im=a.portrait(r,PLAYER if r in ("worker","footman","archer","knight","priest","hero") else ENEMY,150)
    S.blit(im,(i*170+10,10));S.blit(f.render(r,True,(240,230,200)),(i*170+10,170))
pygame.image.save(S,'design/portraits.png');print('saved')
