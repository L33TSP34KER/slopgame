import os,sys,math
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
from src.defs import *
g=Game(parse_args(["--qa","--scene","play"]));w=g.world
for i in range(int(460*30)):
    w.update(1/30)
    if w.state!="playing": break
print("state",w.state,"t",round(w.time,1),"player units",len(w.units_of(PLAYER)),"enemies",len(w.units_of(ENEMY)))
print("player buildings")
for b in w.buildings_of(PLAYER): print(" ",b.bid,round(b.x),round(b.y),round(b.hp),"/",b.max_hp)
print("enemy buildings")
for b in w.buildings_of(ENEMY): print(" ",b.bid,round(b.x),round(b.y),round(b.hp))
halls=[b for b in w.buildings_of(PLAYER) if b.bid in ('townhall','keep')]
print("halls",[(b.bid,round(b.hp)) for b in halls])
for u in w.units_of(ENEMY)[:18]:
    print(u.kind,round(u.x,1),round(u.y,1),"ord",u.order and u.order.get('type'),"tgt",u.target.bid if u.target and u.target.is_building else (u.target.kind if u.target else None),"path",len(u.path) if u.path else None,"cd",round(u.attack_cd,1))
print("wave",w.ai.wave,"next",round(w.ai.next_wave),"pending",len(w.ai.pending))
print("--- cluster detail ---")
cl=[u for u in w.units_of(ENEMY) if 30<u.x<34 and 36<u.y<40]
u=cl[0]
print("u",u.kind,round(u.x,2),round(u.y,2),"path_i",u.path_i,"len",len(u.path) if u.path else None,"stuck",u.stuck_t,"repath",u.repath_t,"eff",u.eff_speed,"stun",u.stun,"slow",u.slow_t)
if u.path:
    nx,ny=u.path[min(u.path_i,len(u.path)-1)]
    print("next",nx,ny,"pass",w._passable(nx,ny,u),"mapblocked",w.map.blocked[w.map.i(int(nx),int(ny))],"h",w.map.height_at(int(nx),int(ny)),"terr",w.map.terr(int(nx),int(ny)),"blockedset",(int(nx),int(ny)) in w.blocked)
print("follow",w.follow_path(u,1/30),"pos",u.x,u.y,"pi",u.path_i,"path",len(u.path) if u.path else None)
print("target",w.nearest_enemy(u,u.sight,team=PLAYER))
print("near own",len([o for o in w.units_of(ENEMY) if math.hypot(o.x-u.x,o.y-u.y)<2]))
print("--- manual walk ---")
print("path slice",u.path[u.path_i-2:u.path_i+4] if u.path else None)
for i in range(30):
    w.follow_path(u,1/30)
    if i%5==0: print(i,round(u.x,2),round(u.y,2),"pi",u.path_i,"path",len(u.path) if u.path else None)
print("--- live 10s ---")
for k in range(10):
    for z in range(30): w.update(1/30)
    print(k+1,round(u.x,2),round(u.y,2),"pi",u.path_i,"path",len(u.path) if u.path else None,"ord",u.order and u.order.get('type'),"stuck",u.stuck_t,"rep",u.repath_t)
