import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
from src.defs import *
g=Game(parse_args(["--qa","--scene","base"]));w=g.world;h=w.hero
h.level=6; h.mana=500
# unit ability on empty ground must not crash
g.targeting={"aid":"ember-lance"}; g.cast_at(800,450); print("lance ground ok",g.targeting)
# unit ability on enemy
e=w.spawn_unit("ghoul",h.x+2,h.y+1,ENEMY); g.targeting={"aid":"ember-lance"}; g.cast_at(*g.screen_pos(e)); print("lance enemy hp",round(e.hp),"cd",h.abil_cd.get("ember-lance"))
# self shield
g.handle_action({"kind":"ability","ability":"aegis"}); print("shield",h.shield_hp)
# ground aoe
h.mana=500; g.targeting={"aid":"consecrate"}; g.cast_at(800,450); print("consecrate ok",g.targeting)
h.mana=500; g.targeting={"aid":"daybreak"}; g.cast_at(800,450); print("daybreak ok",g.targeting)
print("alive, state",h.alive,w.state)
