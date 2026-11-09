import os,sys,math
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
from src.defs import *
g=Game(parse_args(["--qa","--scene","siege"]));w=g.world
for i in range(26):
    u=w.spawn_unit("knight" if i%2 else "archer", 57+(i%6)*0.9, 29+(i//6)*0.9, PLAYER); u.order=None
w.cmd_attack_move([u for u in w.units_of(PLAYER) if not u.worker], 61, 18)
for i in range(int(90*30)): w.update(1/30)
necro=next(b for b in w.entities if b.bid=="necropolis")
print("necro",round(necro.hp),round(necro.x),round(necro.y))
for b in w.buildings_of(ENEMY):
    print("EB",b.bid,round(b.hp),round(b.x),round(b.y))
cnt=0
for u in w.units_of(PLAYER):
    d=math.hypot(u.x-(necro.x+2.5),u.y-(necro.y+2.5))
    if u.order and u.order.get("type")=="attack": cnt+=1
    if u.uid % 5 == 0 or d<8:
        print(u.kind,round(u.x,1),round(u.y,1),"d",round(d,1),"ord",u.order and u.order.get("type"),"tgt",u.target.kind if u.target else None,"path",len(u.path) if u.path else None)
print("attacking",cnt,"of",len(w.units_of(PLAYER)))
print("--- direct query ---")
u=[x for x in w.units_of(PLAYER) if x.kind=='archer'][0]
print("u",u.x,u.y,"sight",u.sight,"team",u.team)
print("nearest any",w.nearest_enemy(u,u.sight))
print("nearest enemy",w.nearest_enemy(u,u.sight,team=ENEMY))
print("near list",[(o.kind,o.team,o.alive,round(o.x,1),round(o.y,1)) for o in w.enemies_near(u,u.sight)][:6])
print("grid necro",any(o.kind=='necropolis' for o in w.grid.query(u.x,u.y,u.sight+3)))
