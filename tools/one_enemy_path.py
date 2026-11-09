import os,sys,math
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
from src.defs import *
g=Game(parse_args(["--qa","--scene","play"]));w=g.world
# remove all enemies except one, place near stuck spot
u=w.spawn_unit("ghoul",32,37,ENEMY)
for e in list(w.entities):
    if e.team==ENEMY and e is not u and not e.is_building:
        e.alive=False
u.order={"type":"attack_move","x":20.0,"y":68.0}
w._set_path(u,(20.0,68.0))
print("path",u.path[:10] if u.path else None,"len",len(u.path) if u.path else None)
for i in range(600):
    w.update(1/30)
    if i%60==0:
        print(i//30,"pos",round(u.x,2),round(u.y,2),"pi",u.path_i,"path",len(u.path) if u.path else None,"ord",u.order and u.order.get('type'),"stuck",round(u.stuck_t,2),"height",u.height)
        if u.path:
            nx,ny=u.path[min(u.path_i,len(u.path)-1)]
            print("  next",nx,ny,"pass",w._passable(nx,ny,u),"mapblocked",w.map.blocked[w.map.i(int(nx),int(ny))],"h",w.map.height_at(int(nx),int(ny)))
    if not u.alive: break
print("final",round(u.x,2),round(u.y,2),"dist hall",round(math.hypot(u.x-20,u.y-68),2),"state",w.state)
