"""Verify siege win + build/train chain on current HEAD (mimo)."""
import os, sys, json, time
sys.path.insert(0, os.path.abspath("."))
os.environ["SDL_VIDEODRIVER"]="dummy"; os.environ["SDL_AUDIODRIVER"]="dummy"; os.environ["EMBERFALL_QA"]="1"
import pygame
from emberfall.src import app as app_mod
from emberfall.src.defs import PLAYER, ENEMY, BUILDINGS

def run(scene, speed, max_t, tag):
    g = app_mod.Game(app_mod.parse_args(["--qa","--scene",scene,"--autoplay","--speed",str(speed)]))
    g.running=True; dt=1/60
    def step(n=1):
        for _ in range(n):
            for ev in pygame.event.get(): g.handle_event(ev)
            g.update(dt); g.draw()
    step(30)
    t0=time.time(); hist=[]
    while g.world.time < max_t and time.time()-t0 < 240 and g.state == "play":
        step(120)
        w=g.world
        b=[e for e in w.entities if getattr(e,"is_building",False) and getattr(e,"team",None)==PLAYER and getattr(e,"alive",False)]
        u=[e for e in w.entities if not getattr(e,"is_building",False) and getattr(e,"alive",False) and getattr(e,"team",None)==PLAYER]
        nec=[e for e in w.entities if getattr(e,"bid",None)=="necropolis" and getattr(e,"alive",False)]
        hist.append({"t":round(w.time,1),"buildings":len(b),"units":len(u),
                     "necropolis":round(sum(getattr(e,"hp",0) for e in nec)),
                     "state":g.state})
    print(json.dumps({"scene":tag,"final_state":g.state,"world_state":getattr(g.world,"state",None),
                      "samples":hist[::max(1,len(hist)//12)],"wall_s":round(time.time()-t0,1)}), flush=True)
    try: pygame.quit()
    except Exception: pass
    return g.state

run("siege", 6, 240, "siege_win")
run("play", 4, 360, "play_first_6min")
