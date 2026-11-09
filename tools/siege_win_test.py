import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
from src.defs import *
g=Game(parse_args(["--qa","--scene","siege"]))
w=g.world
# reinforce the siege so we can test the win path
for i in range(26):
    u=w.spawn_unit("knight" if i%2 else "archer", 57+(i%6)*0.9, 29+(i//6)*0.9, PLAYER)
    u.order=None
w.cmd_attack_move([u for u in w.units_of(PLAYER) if not u.worker], 61, 18)
for i in range(int(90*30)):
    w.update(1/30)
    if w.state!="playing": break
necro=next((b for b in w.entities if b.bid=="necropolis"),None)
print("state",w.state,"t",round(w.time,1),"necro",round(necro.hp) if necro else None,"alive",necro.alive if necro else None)
print("player units",len(w.units_of(PLAYER)),"enemy",len(w.units_of(ENEMY)),"kills",w.stats["kills"],"losses",w.stats["losses"])
print("hero",w.hero.alive if w.hero else None,"level",w.hero.level if w.hero else None)
