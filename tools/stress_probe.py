import os,sys,time,statistics
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
from src.defs import *
g=Game(parse_args(["--qa","--scene","base"]));w=g.world
for i in range(70):
    u=w.spawn_unit("footman" if i%2 else "archer", 28+(i%10)*1.1, 74+(i//10)*1.1, PLAYER); u.order=None
for i in range(24):
    u=w.spawn_unit("ghoul" if i%3 else "fiend", 34+(i%6)*1.1, 70+(i//6)*1.1, ENEMY); u.order={"type":"hold"}
w.gold=9999; w.lumber=9999
times=[]
for i in range(420):
    t=time.perf_counter()
    g.update(1/60); g.draw(); pygame.display.flip()
    times.append(time.perf_counter()-t)
fps=[1/x for x in times[30:]]
print("units",len(w.units_of(PLAYER)),"enemies",len(w.units_of(ENEMY)))
print("mean fps",round(statistics.mean(fps),1),"min",round(min(fps),1),"max",round(max(fps),1))
print("frame ms mean",round(statistics.mean(times[30:])*1000,1),"max",round(max(times[30:])*1000,1))
