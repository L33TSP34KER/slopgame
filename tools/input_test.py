import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
from src.defs import PLAYER, ENEMY
args=parse_args(["--qa","--scene","play","--speed","1"])
g=Game(args)
w=g.world
# select workers and gather
workers=[u for u in w.units_of(PLAYER) if u.worker]
g.select(workers[:2])
print("selected",len(g.selection),"commands",[c['id'] for c in g.ui.commands()])
mine=next(m for m in w.map.mines if not m["neutral"])
w.cmd_gather(workers[:2],{"type":"gold","mine":mine})
# build farm through the real action path
g.ui.build_menu=True
cmds=g.ui.commands(); print("build menu",[c['id'] for c in cmds])
g.handle_action(next(c for c in cmds if c['id']=='build_farm'))
print("placement",g.placement)
# find valid spot and place at its screen position
spot=None
for yy in range(68,78):
    for xx in range(14,30):
        if w.can_place('farm',xx,yy): spot=(xx,yy); break
    if spot: break
print("spot",spot)
px,py=g.renderer.w2s(spot[0]+1,spot[1]+1,1)
mx=px-g.camera.x+800; my=py-g.camera.y+450
g.place_building(mx,my)
print("placement after",g.placement,"farm exists",[b.bid for b in w.buildings_of(PLAYER)])
# train worker
hall=next(b for b in w.buildings_of(PLAYER) if b.bid=='townhall')
w.gold=3000; w.lumber=1000
w.cmd_train(hall,'worker'); print("queue",len(hall.queue))
# hero ability on a dummy enemy near hero
enemy=w.spawn_unit('ghoul',w.hero.x+2,w.hero.y+1,ENEMY)
w.hero.mana=220
w.cmd_cast(w.hero,'ember-lance',enemy)
print("enemy hp after cast",enemy.hp,"mana",w.hero.mana,"cd",w.hero.abil_cd)
# run
for i in range(60*10):
    g.update(1/60)
print("after 10s: gold",w.gold,"units",len(w.units_of(PLAYER)),"farm progress",[round(b.build_progress,2) for b in w.buildings_of(PLAYER) if b.bid=='farm'],"queue",len(hall.queue))
print("alive",w.state,"selection",len(g.selection))
g.ui.draw(g.screen)
g.take_shot('design/shot-inputtest.png')
