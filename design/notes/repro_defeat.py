"""Repro: what happens to fps/state when the player loses everything? (mimo)"""
import os, sys, json, time
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
step(60)
def snap(tag):
    alive=[u for u in g.world.entities if getattr(u,"alive",False)]
    pa=[u for u in alive if getattr(u,"team",None)==PLAYER]
    print(json.dumps({"tag":tag,"state":g.state,"mode":getattr(g.world,"state",None),
        "player_alive":len(pa),"total_alive":len(alive),
        "fps":round(g.clock.get_fps() or 0,1)}), flush=True)
snap("baseline")
t0=time.time()
for i in range(6):
    for u in list(g.world.entities):
        if getattr(u,"team",None)==PLAYER and getattr(u,"alive",False):
            u.alive=False; u.hp=0
    t=time.time()
    step(30)
    print(json.dumps({"tag":f"wipe+30f_{i}","wall_s":round(time.time()-t,2),
                      "state":g.state,"mode":getattr(g.world,"state",None)}), flush=True)
snap("after_wipes")
