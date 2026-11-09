import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
g=Game(parse_args([]))
print("state",g.state)
g.ui.draw(g.screen)
act=g.ui.take_action((800,462))
print("title action",act)
g.handle_action(act)
print("after campaign",g.state,g.world.started)
g.ui.draw(g.screen)
# find begin action
beg=None
for a in g.ui.actions:
    if a.get("action")=="begin": beg=a; break
print("begin",beg)
g.handle_action(beg)
print("after begin",g.state,g.world.started)
# pause / settings / back
g.handle_key(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_ESCAPE,unicode='\x1b'))
print("paused",g.state)
g.ui.draw(g.screen)
for a in g.ui.actions:
    if a.get("action")=="settings": g.handle_action(a); break
print("settings",g.state)
g.ui.draw(g.screen)
for a in g.ui.actions:
    if a.get("action")=="back": g.handle_action(a); break
print("back",g.state)
# tooltips: simulate hover over a hero ability and draw
hero=g.world.hero; g.select([hero]); g.ui.draw(g.screen)
for a in g.ui.actions:
    if a.get("kind")=="ability": g.ui.mouse=a["rect"].center; break
g.ui.draw(g.screen); print("tooltip",g.ui.hover_action and g.ui.hover_action.get("label"))
