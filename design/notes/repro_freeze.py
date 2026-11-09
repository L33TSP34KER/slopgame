"""Reproduce the late-game fps collapse and profile it (mimo)."""
import os, sys, json, time, cProfile, pstats, io
sys.path.insert(0, os.path.abspath("."))
os.environ["SDL_VIDEODRIVER"]="dummy"; os.environ["SDL_AUDIODRIVER"]="dummy"; os.environ["EMBERFALL_QA"]="1"
import pygame
from emberfall.src import app as app_mod
from emberfall.src.defs import PLAYER, ENEMY

g = app_mod.Game(app_mod.parse_args(["--qa","--scene","play"]))
g.running=True
dt=1/60
def step(n=1):
    for _ in range(n):
        for ev in pygame.event.get(): g.handle_event(ev)
        g.update(dt); g.draw()
def counts(tag):
    w=g.world
    alive=[u for u in w.entities if getattr(u,"alive",False)]
    print(json.dumps({"tag":tag,"player":len([u for u in alive if getattr(u,"team",None)==PLAYER]),
        "enemy":len([u for u in alive if getattr(u,"team",None)!=PLAYER]),
        "particles":len(w.particles),"corpses":len([u for u in w.entities if not getattr(u,"alive",False)]),
        "time":round(getattr(w,"time",0),1)}), flush=True)
step(60); counts("start")
# teleport every enemy next to the player hall so they siege immediately
hall=[u for u in g.world.entities if getattr(u,"is_building",False) and getattr(u,"team",None)==PLAYER]
hx,hy=(hall[0].x,hall[0].y) if hall else (20,66)
n=0
for e in g.world.entities:
    if getattr(e,"team",None)!=PLAYER and not getattr(e,"is_building",False) and getattr(e,"alive",False):
        e.x = hx + 4 + (n%6); e.y = hy + 3 + (n//6)*0.8; e.path=None; n+=1
counts("enemies teleported")
# kill player mobile units so only buildings remain (mirrors qa-02 state)
for u in g.world.entities:
    if getattr(u,"team",None)==PLAYER and not getattr(u,"is_building",False) and getattr(u,"alive",False):
        u.alive=False; u.hp=0
counts("player army wiped")
for i in range(8):
    t=time.time(); step(60); wall=time.time()-t
    print(json.dumps({"block":i,"wall_s":round(wall,2),"fps_equiv":round(60/wall,1)}), flush=True)
    counts(f"block{i}")
# profile 90 frames at the collapse point
pr=cProfile.Profile(); pr.enable()
step(90)
pr.disable()
s=io.StringIO(); st=pstats.Stats(pr,stream=s); st.sort_stats("tottime"); st.print_stats(14)
print(s.getvalue()[:3000], flush=True)
