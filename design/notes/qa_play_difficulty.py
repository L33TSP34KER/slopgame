"""Pacing evidence: does the real mission scene differ across difficulties?"""
import os, sys, json, time
sys.path.insert(0, os.path.abspath("."))
os.environ["SDL_VIDEODRIVER"]="dummy"; os.environ["SDL_AUDIODRIVER"]="dummy"; os.environ["EMBERFALL_QA"]="1"
import pygame
from emberfall.src import app as app_mod
from emberfall.src.defs import PLAYER

def run(diff, speed=4.0, cap=520.0):
    g = app_mod.Game(app_mod.parse_args(["--qa","--scene","play","--autoplay",
                                         "--speed",str(speed),"--difficulty",diff]))
    g.running=True; dt=1/60
    def step(n=1):
        for _ in range(n):
            for ev in pygame.event.get(): g.handle_event(ev)
            g.update(dt); g.draw()
    step(60)
    t0=time.time(); state="play"; hist=[]
    while state=="play" and time.time()-t0 < 420 and g.world.time < cap:
        step(180)
        w=g.world
        hall=max([b.hp for b in w.buildings_of(PLAYER) if b.bid in ("townhall","keep")] or [0])
        hist.append({"t":round(w.time,1),"hall":hall,"units":len(w.units_of(PLAYER)),
                     "wave":getattr(getattr(w,"ai",None),"wave",0)})
        state=g.state
    res={"difficulty":diff,"outcome":state,"end_t":round(g.world.time,1),
         "waves":sorted({h["wave"] for h in hist if h["wave"]}),
         "last":hist[-1] if hist else None,
         "hall_at_180":next((h["hall"] for h in hist if h["t"]>=180), None),
         "lumber_gathered":g.world.stats["lumber_gathered"]}
    try: pygame.quit()
    except Exception: pass
    return res

out=[]
for d in ("squire","knight","warlord"):
    out.append(run(d))
print(json.dumps({"qa":{"play_difficulty":out}}, indent=1))
