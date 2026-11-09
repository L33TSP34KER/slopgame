import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame;pygame.init();pygame.display.set_mode((1,1))
from src.mapgen import generate_map
from src.world import World
from src.defs import *
class D:
    sfx=None
    def shake(self,*a):pass
    def on_mission_end(self,r): print("ON_END",r)
m=generate_map();w=World(D(),m,None,"knight");w.started=True
necro=next(b for b in w.buildings_of(ENEMY) if b.bid=="necropolis")
w.damage(necro,99999,w.hero,"normal")
print("after necro:",w.state, w.entities and len([e for e in w.entities if e.alive]))
w2=World(D(),m,None,"knight");w2.started=True
for b in list(w2.buildings_of(PLAYER)): w2.damage(b,99999,None,"normal")
for u in list(w2.units_of(PLAYER)): w2.damage(u,99999,None,"normal")
for i in range(5): w2.update(1/30)
print("after wipe:",w2.state)
