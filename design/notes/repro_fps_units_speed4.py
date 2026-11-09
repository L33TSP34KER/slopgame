"""Repro: fps when the player has no mobile units left but buildings remain."""
import os, sys, json, time
sys.path.insert(0, os.path.abspath("."))
os.environ["SDL_VIDEODRIVER"]="dummy"; os.environ["SDL_AUDIODRIVER"]="dummy"; os.environ["EMBERFALL_QA"]="1"
import pygame
from emberfall.src import app as app_mod
from emberfall.src.defs import PLAYER
g = app_mod.Game(app_mod.parse_args(["--qa","--scene","play","--speed","4"]))
g.running=True
dt=1/60
def step(n=1):
    for _ in range(n):
        for ev in pygame.event.get(): g.handle_event(ev)
        g.update(dt); g.draw()
def stats(tag):
    alive=[u for u in g.world.entities if getattr(u,"alive",False)]
    pa=[u for u in alive if getattr(u,"team",None)==PLAYER and not getattr(u,"is_building",False)]
    pb=[u for u in alive if getattr(u,"team",None)==PLAYER and getattr(u,"is_building",False)]
    ea=[u for u in alive if getattr(u,"team",None)!=PLAYER]
    print(json.dumps({"tag":tag,"state":g.state,"mode":getattr(g.world,"state",None),
        "player_units":len(pa),"player_bldg":len(pb),"enemies":len(ea),
        "total":len(alive)}), flush=True)
step(60); stats("baseline")
# wipe ONLY player mobile units, keep buildings (no defeat expected)
for u in list(g.world.entities):
    if getattr(u,"team",None)==PLAYER and not getattr(u,"is_building",False) and getattr(u,"alive",False):
        u.alive=False; u.hp=0
stats("after_wipe_units")
for i in range(6):
    t=time.time(); step(30); wall=time.time()-t
    print(json.dumps({"tag":f"30f_{i}","wall_s":round(wall,2),"fps_equiv":round(30/wall,1),
                      "state":g.state,"mode":getattr(g.world,"state",None)}), flush=True)
stats("end")
