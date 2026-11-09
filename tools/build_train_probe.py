import os,sys,math
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
from src.defs import *
args=parse_args([])
g=Game(args); g.start_mission(skip_intro=True); w=g.world
w.gold=2000; w.lumber=800
step=1/30
# select one worker
worker=[u for u in w.units_of(PLAYER) if u.worker][0]
g.select([worker])
# use the real UI action path
g.handle_action({"kind":"buildmenu"})
print("menu open",g.ui.build_menu,"cmds",[c['id'] for c in g.ui.commands()][:4])
g.handle_action({"kind":"build","bid":"farm"})
print("placement",g.placement)
spot=None
for yy in range(66,78):
    for xx in range(10,30):
        if w.can_place('farm',xx,yy): spot=(xx,yy); break
    if spot: break
print("farm spot",spot)
px,py=g.renderer.w2s(spot[0]+1,spot[1]+1,1)
g.place_building(px-g.camera.x+800, py-g.camera.y+450)
print("farm built",[(b.bid,round(b.build_progress,2)) for b in w.buildings_of(PLAYER) if b.bid=='farm'],"placement",g.placement)
for i in range(int(25/step)): w.update(step)
print("farm after 25s",[(b.bid,round(b.build_progress,2)) for b in w.buildings_of(PLAYER) if b.bid=='farm'])
# build barracks directly next to hall, then train
for yy in range(62,76):
    for xx in range(20,32):
        if w.can_place('barracks',xx,yy): bspot=(xx,yy); break
    else: continue
    break
print("barracks spot",bspot)
b=w.cmd_build([worker],"barracks",*bspot)
print("barracks queued",bool(b))
for i in range(int(30/step)): w.update(step)
print("barracks progress",round(b.build_progress,2) if b else None,"gold",w.gold,"lumber",w.lumber)
if b and b.build_progress>=1:
    before=len(w.units_of(PLAYER)); w.cmd_train(b,'footman'); print("train queue",len(b.queue))
    for i in range(int(25/step)): w.update(step)
    print("units before/after",before,len(w.units_of(PLAYER)),"queue",len(b.queue))
# stacking measure
g2=Game(parse_args(["--qa","--scene","base"])); w2=g2.world
for i in range(int(6/60*60*4)): g2.update(1/60)
units=w2.units_of(PLAYER)
mind=99; pair=None
for i in range(len(units)):
    for j in range(i+1,len(units)):
        d=math.hypot(units[i].x-units[j].x,units[i].y-units[j].y)
        if d<mind: mind=d; pair=(units[i].kind,units[j].kind)
print("min unit distance after 6s",round(mind,2),pair,"n",len(units))
print("build_train done")
