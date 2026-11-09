import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame;pygame.init();pygame.display.set_mode((1,1))
from src.mapgen import generate_map
from src.world import World
from src.pathfind import find_path, walkable, can_step
from src.defs import *
class D:
    sfx=None
    def shake(self,*a):pass
    def on_mission_end(self,r):pass
m=generate_map();w=World(D(),m,None,"knight");w.ai=None;w.started=True
gh=w.spawn_unit("ghoul",36.58,34.4,ENEMY)
w.entities=[gh]
for pos in [(36,34),(36,35),(36,36),(36,37),(37,36)]:
    print(pos,"walk",walkable(m,*pos,w.blocked),"mapblocked",m.blocked[m.i(*pos)],"height",m.height_at(*pos),"ramp",m.ramp[m.i(*pos)])
p=find_path(m,(36.58,34.4),(20,68),extra=w.blocked)
print("path",p)
w.cmd_attack_move([gh],20,68)
step=1/30
for i in range(90):
    w.update(step)
    if i<12 or i%10==0:
        print(i,"pos",round(gh.x,2),round(gh.y,2),"path",gh.path,"pi",gh.path_i,"order",gh.order)
print("--- manual follow ---")
gh.x,gh.y=36.5,34.5; gh.path=[(36.5,34.5),(38.5,33.5)]; gh.path_i=1; gh.eff_speed=3.0
print("before",gh.x,gh.y,"passable next", w._passable(36.54,34.53,gh))
print("follow ret", w.follow_path(gh,1/30), "pos",gh.x,gh.y, "path",gh.path, "pi",gh.path_i)
print("target", gh.target, "order", gh.order)
