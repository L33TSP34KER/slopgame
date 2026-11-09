"""Reach the real late-game freeze under --autoplay, then profile it (mimo)."""
import os, sys, json, time, cProfile, pstats, io
sys.path.insert(0, os.path.abspath("."))
os.environ["SDL_VIDEODRIVER"]="dummy"; os.environ["SDL_AUDIODRIVER"]="dummy"
os.environ["EMBERFALL_QA"]="state"; os.environ["EMBERFALL_AUTOPLAY"]="1"
import pygame
from emberfall.src import app as app_mod
from emberfall.src.defs import PLAYER

g = app_mod.Game(app_mod.parse_args(["--qa","--scene","play","--autoplay","--speed","6"]))
g.running=True
dt=1/60
def step(n=1):
    for _ in range(n):
        for ev in pygame.event.get(): g.handle_event(ev)
        g.update(dt); g.draw()
def counts(tag):
    w=g.world
    alive=[u for u in w.entities if getattr(u,"alive",False)]
    print(json.dumps({"tag":tag,"t":round(w.time,1),"player":len([u for u in alive if getattr(u,"team",None)==PLAYER]),
        "enemy":len([u for u in alive if getattr(u,"team",None)!=PLAYER]),
        "particles":len(w.particles),
        "wave":getattr(getattr(w,"ai",None),"wave",0)}), flush=True)

target_t = float(sys.argv[1]) if len(sys.argv)>1 else 420.0
t0=time.time(); last=0
while g.world.time < target_t and time.time()-t0 < 420:
    t=time.time(); step(60); wall=time.time()-t
    if g.world.time - last >= 30 or wall > 5:
        print(json.dumps({"t":round(g.world.time,1),"block_wall_s":round(wall,2),"fps_equiv":round(60/wall,1),
                          "state":g.state}), flush=True)
        last=g.world.time
    if wall > 20:
        print(json.dumps({"WARN":"block slower than 20s","wall":round(wall,2)}), flush=True)
        break
counts("pre_profile")
pr=cProfile.Profile(); pr.enable()
step(60)
pr.disable()
s=io.StringIO(); st=pstats.Stats(pr,stream=s); st.sort_stats("tottime"); st.print_stats(16)
print("=== PROFILE AT FREEZE ===", flush=True)
print(s.getvalue()[:3500], flush=True)
counts("post_profile")
