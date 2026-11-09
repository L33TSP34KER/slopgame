import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.app import Game, parse_args
from src.defs import *
g=Game(parse_args([]));g.start_mission(skip_intro=True);w=g.world
w.gold=8000;w.lumber=4000
# farms for food
for bid,spot in (("farm",(12,70)),("farm",(14,72)),("farm",(10,74))):
    if w.can_place(bid,*spot): w.spawn_building(bid,*spot,PLAYER)
w.spawn_building("barracks",24,62,PLAYER)
w.spawn_building("blacksmith",17,74,PLAYER)
w.spawn_building("keep",20,60,PLAYER)
w.spawn_building("altar",14,76,PLAYER)
w.update_fog(force=True)
# hero xp/level
h=w.hero
print("start lvl",h.level,"xp",h.xp)
enemy=w.spawn_unit("ghoul",h.x+1.2,h.y+0.5,ENEMY)
w.damage(enemy,99999,h,"normal")
print("after kill lvl",h.level,"xp",h.xp)
w.gain_xp(h,900)
print("after xp lvl",h.level,"maxhp",h.max_hp,"mana",h.max_mana,"unlocks",[k for k,a in ABILITIES.items() if h.level>=a['unlock']])
# research
bs=next(b for b in w.buildings_of(PLAYER) if b.bid=='blacksmith')
w.cmd_research(bs,"weapons1")
for i in range(int(32*30)): w.update(1/30)
print("upgrades",w.upgrades,"dmg_bonus",w.dmg_bonus,"research",bs.research)
# knight
b=next(b for b in w.buildings_of(PLAYER) if b.bid=='barracks')
before=len([u for u in w.units_of(PLAYER) if u.kind=='knight'])
w.cmd_train(b,'knight'); print("queue",len(b.queue),"food",w.food_used(PLAYER),"/",w.food_max(PLAYER))
for i in range(int(31*30)): w.update(1/30)
print("knights",before,"->",len([u for u in w.units_of(PLAYER) if u.kind=='knight']),"queue",len(b.queue))
# hero revive
h=w.hero; w.damage(h,99999,None,"normal"); print("hero dead",h.alive,"revive",h.hero_revive_t)
for i in range(int(47*30)): w.update(1/30)
print("hero revived",bool(w.hero and w.hero.alive),"lvl",w.hero.level if w.hero else None,"state",w.state)
# building damage bonus check: attack a dummy building? print unit dmg range vs bonus
print("footman dmg",[(u.dmg_min,u.dmg_max) for u in w.units_of(PLAYER) if u.kind=='footman'][:1],"bonus",w.dmg_bonus)
