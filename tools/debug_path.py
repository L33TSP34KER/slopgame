import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame;pygame.init();pygame.display.set_mode((1,1))
from src.mapgen import generate_map
from src.world import World
from src.ai import EnemyAI
from src.pathfind import find_path, walkable
from src.defs import *
class D:
    sfx=None
    def shake(self,*a):pass
    def on_mission_end(self,r):pass
m=generate_map();w=World(D(),m,None,"knight");w.ai=EnemyAI(w);w.started=True
print("walk 35,34", walkable(m,35,34,w.blocked), "height",m.height_at(35,34))
p=find_path(m,(35.2,34.9),(20,68),extra=w.blocked)
print("path 35,34 ->20,68", p[:12] if p else None, len(p) if p else 0)
p2=find_path(m,(35,34),(36,37),extra=w.blocked)
print("path to ramp", p2)
step=1/30
# find a ghoul and force attack move
gh=[u for u in w.units_of(ENEMY) if u.kind=="ghoul"][0]
gh.x,gh.y=35.2,34.9
w.cmd_attack_move([gh],20,68)
for i in range(int(8/step)):
    w.update(step)
    if i%30==0:
        print(i//30,"pos",round(gh.x,2),round(gh.y,2),"order",gh.order and gh.order.get('type'),"path",len(gh.path) if gh.path else None,"pi",gh.path_i,"stuck",round(gh.stuck_t,2), "height",gh.height)
print("walkable now", walkable(m,int(gh.x),int(gh.y),w.blocked), "blocked tile?", (int(gh.x),int(gh.y)) in w.blocked)
