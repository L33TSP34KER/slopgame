import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame;pygame.init();pygame.display.set_mode((1,1))
from src.mapgen import generate_map
from src.world import World
from src.ai import EnemyAI
from src.defs import *
from src.pathfind import find_path
class D:
    sfx=None
    def shake(self,*a):pass
    def on_mission_end(self,r):print("END",r)
m=generate_map();w=World(D(),m,None,"knight");w.ai=EnemyAI(w);w.started=True
# direct path check enemy base to player hall
p=find_path(m,(61,24),(24,70),extra=w.blocked)
print("path enemy->player", len(p) if p else None, p[:3] if p else None)
step=1/30
for i in range(int(260/step)): w.update(step)
print("time",w.time,"wave",w.ai.wave,"next",w.ai.next_wave,"enemy units",len(w.units_of(ENEMY)))
for u in w.units_of(ENEMY)[:12]:
    print(u.kind, round(u.x,1),round(u.y,1), u.order, "path", len(u.path) if u.path else None)
ph=w.buildings_of(PLAYER)
print("player buildings",[(b.bid,round(b.x),round(b.y),round(b.hp)) for b in ph],"hero alive",w.hero.alive if w.hero else None)
# archer test isolated on flat ground near base
w2=World(D(),m,None,"knight");w2.ai=None;w2.started=True
a=w2.spawn_unit("archer",25,69,PLAYER); g=w2.spawn_unit("ghoul",29,69,ENEMY)
w2.cmd_attack([a],g)
for i in range(int(8/step)):
    w2.update(step)
    if i%15==0: print("arch",round(a.hp),round(g.hp),a.order,"path",len(a.path) if a.path else None,"dist",round(((a.x-g.x)**2+(a.y-g.y)**2)**.5,2))
print("archer kills",w2.stats)
