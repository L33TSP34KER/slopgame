import os,sys,math
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
from src.defs import *
g=Game(parse_args(["--qa","--scene","play"]));w=g.world
for i in range(int(260*30)):
    w.update(1/30)
stuck=[u for u in w.units_of(ENEMY) if u.order and u.order.get("type")=="attack_move"]
print("stuck count",len(stuck))
u=stuck[0]
print("pos",u.x,u.y,"pathlen",len(u.path) if u.path else None,"pi",u.path_i,"stuck",u.stuck_t,"eff",u.eff_speed,"order",u.order)
print("path",u.path[:8] if u.path else None)
if u.path:
    nx,ny=u.path[min(u.path_i,len(u.path)-1)]
    print("next",nx,ny,"tile",int(nx),int(ny),"mapblocked",w.map.blocked[w.map.i(int(nx),int(ny))],"terr",w.map.terr(int(nx),int(ny)),"h",w.map.height_at(int(nx),int(ny)),"worldblocked",(int(nx),int(ny)) in w.blocked,"passable",w._passable(nx,ny,u))
for i in range(5):
    for k in range(30): w.update(1/30)
    print("t+",i+1,"pos",round(u.x,2),round(u.y,2),"pi",u.path_i,"path",len(u.path) if u.path else None,"stuck",round(u.stuck_t,2))
print("local units",[(round(o.x,1),round(o.y,1)) for o in w.units_of(ENEMY) if math.hypot(o.x-u.x,o.y-u.y)<2.5][:10])
print("--- detail ---")
u=stuck[0]
print("u pos",u.x,u.y,"path_i",u.path_i,"stuck",u.stuck_t,"repath",u.repath_t,"stun",u.stun,"eff",u.eff_speed)
print("nearest player",w.nearest_enemy(u,u.sight,team=PLAYER))
if u.path:
    nx,ny=u.path[min(u.path_i,len(u.path)-1)]
    print("next",nx,ny,"pass",w._passable(nx,ny,u),"mapblocked",w.map.blocked[w.map.i(int(nx),int(ny))])
print("manual follow",w.follow_path(u,1/30),"pos",u.x,u.y,"pi",u.path_i,"path",len(u.path) if u.path else None)
for k in range(30): w.update(1/30)
print("5s pos",u.x,u.y,"pi",u.path_i,"path",len(u.path) if u.path else None,"ord",u.order and u.order.get('type'),"stuck",u.stuck_t)
t=w.nearest_enemy(u,u.sight,team=PLAYER)
print("TARGET",t.kind if t else None,t.team if t else None,round(t.x,1) if t else None,round(t.y,1) if t else None,t.is_building if t else None,t.hp if t else None,t.bid if t and t.is_building else None)
if t:
    d=math.hypot(u.x-(t.x+(t.bw/2 if t.is_building else 0)),u.y-(t.y+(t.bh/2 if t.is_building else 0)))-(max(t.bw,t.bh)*0.52 if t.is_building else 0)
    print("d",round(d,2),"range",u.range,"nearwalk",__import__('src.pathfind',fromlist=['nearest_walkable']).nearest_walkable(w.map,int(t.x),int(t.y),w.blocked,4))
