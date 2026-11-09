"""Difficulty check: squire vs knight vs warlord must feel different (mimo)."""
import os, sys, json, time
sys.path.insert(0, os.path.abspath("."))
os.environ["SDL_VIDEODRIVER"]="dummy"; os.environ["SDL_AUDIODRIVER"]="dummy"; os.environ["EMBERFALL_QA"]="1"
import pygame
from emberfall.src import app as app_mod
from emberfall.src.defs import PLAYER, ENEMY

def run(diff, scene="siege", speed=6.0, window=260.0):
    g = app_mod.Game(app_mod.parse_args(["--qa","--scene",scene,"--autoplay","--speed",str(speed),"--difficulty",diff]))
    g.running=True; dt=1/60
    def step(n=1):
        for _ in range(n):
            for ev in pygame.event.get(): g.handle_event(ev)
            g.update(dt); g.draw()
    step(60)
    t0=time.time(); hist=[]; waves=set(); state=g.state
    while state=="play" and time.time()-t0 < window:
        step(180)
        w=g.world
        waves.add(getattr(getattr(w,"ai",None),"wave",0))
        alive=[e for e in w.entities if getattr(e,"alive",False)]
        hist.append({"t":round(w.time,1),
                     "enemies":len([e for e in alive if getattr(e,"team",None)!=PLAYER]),
                     "player":len([e for e in alive if getattr(e,"team",None)==PLAYER])})
        state=g.state
    res={"difficulty":diff,"scene":scene,"outcome":state,"world":getattr(g.world,"state",None),
         "waves_seen":sorted(w for w in waves if w),
         "end_game_t":round(g.world.time,1),
         "last":hist[-1] if hist else None,
         "enemy_peak":max((h["enemies"] for h in hist), default=0),
         "wall_s":round(time.time()-t0,1)}
    try: pygame.quit()
    except Exception: pass
    return res

out=[]
for d in ("squire","knight","warlord"):
    out.append(run(d))
print(json.dumps({"qa":{"difficulty_results":out}}, indent=1))
