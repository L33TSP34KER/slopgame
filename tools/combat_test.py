import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame; pygame.init(); pygame.display.set_mode((1,1))
from src.mapgen import generate_map
from src.world import World
from src.ai import EnemyAI
from src.defs import *
class Dummy:
    sfx=None
    def shake(self,*a): pass
    def on_mission_end(self,r): print("END",r)
m=generate_map(); w=World(Dummy(),m,None,"knight"); w.ai=EnemyAI(w); w.started=True
# spawn a skirmish
f=w.spawn_unit("footman",52,24,PLAYER); g=w.spawn_unit("ghoul",54,24,ENEMY)
a=w.spawn_unit("archer",50,25,PLAYER); z=w.spawn_unit("zombie" if False else "ghoul",55,25,ENEMY)
h=w.hero
w.cmd_attack([f,a],g); w.cmd_attack([h],z)
step=1/30
for i in range(int(20/step)):
    w.update(step)
    if i%30==0:
        print(f"t={w.time:.1f} footman {f.hp:.0f}/{f.max_hp} ghoul {g.hp:.0f} archer {a.hp:.0f} ghoul2 {z.hp:.0f} hero {h.hp:.0f} alive={sum(1 for e in w.entities if e.alive)}")
    if not (f.alive and g.alive): break
print("kills",w.stats['kills'],"hero xp",h.xp,"lvl",h.level)
# ability test
if h.alive:
    tgt=w.nearest_enemy(h,30)
    print("cast target",tgt)
    w.cmd_cast(h,"ember-lance",tgt)
    for i in range(30): w.update(step)
    print("mana",h.mana,"cd",h.abil_cd)
# long run AI waves
w2=World(Dummy(),m,None,"knight"); w2.ai=EnemyAI(w2); w2.started=True
import time; t0=time.time()
for i in range(int(260/step)):
    w2.update(step)
print("long run", round(time.time()-t0,2),"s state",w2.state,"enemy units",len(w2.units_of(ENEMY)),"player buildings",len(w2.buildings_of(PLAYER)))
print("waves", w2.ai.wave, "alerts", [a['text'] for a in w2._alerts])
