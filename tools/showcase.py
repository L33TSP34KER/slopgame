import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
from src.defs import *
g=Game(parse_args(["--qa","--scene","base"]));w=g.world
for i in range(len(w.explored)): w.explored[i]=1; w.vis[i]=1
w.mode='play'
# add a keep for the player showcase
if w.can_place('keep', 20, 58): w.spawn_building('keep',20,58,PLAYER)
g.center_camera(60,18)
for k in range(3): g.draw()
g.take_shot('design/shot-enemybase.png')
g.center_camera(22,66)
for k in range(3): g.draw()
g.take_shot('design/shot-keep.png')
# building sheet via Art
art=g.art
bids=["townhall","keep","farm","barracks","mill","blacksmith","sanctum","tower","altar","necropolis","ziggurat","crypt","slaughterhouse","temple","bonetower","altarhollow"]
S=pygame.Surface((4*330,4*300),pygame.SRCALPHA); S.fill((26,24,30))
for i,b in enumerate(bids):
    x=(i%4)*330; y=(i//4)*300
    team=ENEMY if BUILDINGS[b].get("enemy") else PLAYER
    img,ax,ay=art.building(b,team,4)
    sc=min(280/img.get_width(),230/img.get_height(),1.0)
    im=pygame.transform.smoothscale(img,(int(img.get_width()*sc),int(img.get_height()*sc)))
    S.blit(im,(x+165-im.get_width()//2,y+240-im.get_height()))
    lab=art.font(16,"serif").render(b,True,(232,220,194)); S.blit(lab,(x+165-lab.get_width()//2,y+250))
pygame.image.save(S,'design/building-sheet-v2.png'); print("saved showcase")
