"""Soak-lite: watch what grows when the AI waves fight (mimo)."""
import os, sys, json, time
sys.path.insert(0, os.path.abspath("."))
os.environ["SDL_VIDEODRIVER"]="dummy"; os.environ["SDL_AUDIODRIVER"]="dummy"; os.environ["EMBERFALL_QA"]="1"
import pygame
from emberfall.src import app as app_mod
from emberfall.src.defs import PLAYER
argv = ["--qa","--scene","play","--speed","4"]
g = app_mod.Game(app_mod.parse_args(argv))
g.running=True
dt=1/60
def step(n=1):
    for _ in range(n):
        for ev in pygame.event.get(): g.handle_event(ev)
        g.update(dt); g.draw()
def counts():
    w=g.world
    out={"t":round(getattr(w,"time",0),1),"state":g.state,"mode":getattr(w,"state",None)}
    out["particles"]=len(getattr(w,"particles",[]) or [])
    out["projectiles"]=len(getattr(w,"projectiles",[]) or [])
    out["entities"]=len(getattr(w,"entities",[]) or [])
    alive=[u for u in getattr(w,"entities",[]) if getattr(u,"alive",False)]
    out["alive"]=len(alive)
    out["player"]=len([u for u in alive if getattr(u,"team",None)==PLAYER])
    out["wave"]=getattr(getattr(w,"ai",None),"wave",0)
    # graphics caches
    for name in ("fx","effects","floating","texts","markers","corpses","trails"):
        v=getattr(w,name,None)
        if isinstance(v,(list,tuple,dict)): out[name]=len(v)
    art=getattr(g,"art",None)
    if art is not None:
        out["art_props"]=len(getattr(art,"props",{}) or {})
        out["art_units"]=len(getattr(art,"unit_cache",{}) or getattr(art,"units",{}) or {})
    return out
step(90)
print("START", json.dumps(counts()), flush=True)
block=0; t=time.time()
for i in range(1,13):
    step(300)
    wall=time.time()-t; t=time.time()
    s=counts(); s["fps_equiv"]=round(300/wall,1)
    print(json.dumps(s), flush=True)
    if wall > 60: break
