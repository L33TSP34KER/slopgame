"""Definitive bisect: split update vs draw time during the real autoplay run."""
import os, sys, json, time
sys.path.insert(0, os.path.abspath("."))
os.environ["SDL_VIDEODRIVER"]="dummy"; os.environ["SDL_AUDIODRIVER"]="dummy"
os.environ["EMBERFALL_QA"]="1"; os.environ["EMBERFALL_AUTOPLAY"]="1"
import pygame
from emberfall.src import app as app_mod
from emberfall.src import pathfind as pf
from emberfall.src import world as wd
from emberfall.src import core as co
from emberfall.src.defs import PLAYER

# counters
C = {"find_path":0, "enemies_near":0, "query":0, "can_step":0}
_of = pf.find_path; _en = wd.World.enemies_near; _q = co.SpatialHash.query; _cs = pf.can_step
def fp(*a, **k):
    C["find_path"] += 1; return _of(*a, **k)
def en(self, *a, **k):
    C["enemies_near"] += 1; return _en(self, *a, **k)
def q(self, *a, **k):
    C["query"] += 1; return _q(self, *a, **k)
def cs(*a, **k):
    C["can_step"] += 1; return _cs(*a, **k)
pf.find_path = fp; wd.World.enemies_near = en; co.SpatialHash.query = q; pf.can_step = cs
import emberfall.src.world as wmod
if hasattr(wmod, "find_path"): wmod.find_path = fp
if hasattr(wmod, "query"): wmod.query = q

g = app_mod.Game(app_mod.parse_args(["--qa","--scene","play","--autoplay","--speed","3"]))
g.running=True
dt=1/60

def one_frame():
    for ev in pygame.event.get(): g.handle_event(ev)
    t0=time.perf_counter(); g.update(dt); t1=time.perf_counter(); g.draw(); t2=time.perf_counter()
    return t1-t0, t2-t1

t_start=time.time(); block_u=block_d=0.0; frames=0; marks=dict(C)
while time.time()-t_start < 420:
    u,d = one_frame(); block_u+=u; block_d+=d; frames+=1
    if frames % 60 == 0:
        w=g.world
        alive=[e for e in w.entities if getattr(e,"alive",False)]
        dc={k: C[k]-marks[k] for k in C}; marks=dict(C)
        print(json.dumps({
            "t":round(w.time,1),"frames":frames,
            "upd_ms":round(block_u*1000/max(1,frames),1),
            "draw_ms":round(block_d*1000/max(1,frames),1),
            "fps_equiv":round(frames/max(1e-6,block_u+block_d),1),
            "player":len([e for e in alive if getattr(e,"team",None)==PLAYER]),
            "enemy":len([e for e in alive if getattr(e,"team",None)!=PLAYER]),
            "corpses":len(w.entities)-len(alive),
            "per_frame":{k: round(v/60,1) for k,v in dc.items()},
            "state":g.state}), flush=True)
        block_u=block_d=0.0; frames=0
        if (C["enemies_near"]/max(1,sum(C.values()))) > 0 and time.time()-t_start > 400:
            break
print("done", json.dumps(C), flush=True)
