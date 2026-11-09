import os,sys,cProfile,pstats,io
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
# warm up
for i in range(40): g.update(1/60); g.draw()
pr=cProfile.Profile(); pr.enable()
for i in range(180):
    g.update(1/60); g.draw(); pygame.display.flip()
pr.disable()
s=io.StringIO(); ps=pstats.Stats(pr,stream=s).sort_stats('cumulative'); ps.print_stats(22); print(s.getvalue())
