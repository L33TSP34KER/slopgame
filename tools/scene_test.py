import os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy"); os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame
pygame.init(); pygame.display.set_mode((1600, 900))
from src.mapgen import generate_map
from src.art import Art
from src.render import Renderer, Camera
from src.defs import *

class E:
    def __init__(self, **kw):
        self.alive=True; self.selected=False; self.death_t=0; self.carry=0
        self.is_building=False; self.build_progress=1.0; self.facing_bucket=0
        self.anim="idle"; self.anim_t=0.0; self.height=1; self.team=PLAYER
        self.hp=100; self.max_hp=100; self.mana=0; self.max_mana=0; self.is_hero=False
        self.__dict__.update(kw)

class G:
    def __init__(self, m, art):
        self.map, self.art = m, art
        self.entities=[]; self.projectiles=[]; self.particles=[]
        self.vis=bytearray([1])*(m.w*m.h); self.explored=bytearray([1])*(m.w*m.h)
        self.selection=[]; self.placement=None; self.drag_start=self.drag_now=None
        self.attack_move_mode=False; self.targeting=False; self.mouse_tile=(20,68)
        self.mode="play"; self.debug=False; self.fps=60
        self.placement_valid=lambda x,y: True

m=generate_map(); art=Art(); g=G(m,art); r=Renderer(g)

def unit(rig, x,y,team=PLAYER, facing=0, anim="idle"):
    t=UNITS[rig]
    u=E(rig=rig, team=team, x=x,y=y,facing_bucket=facing, anim=anim,
        hp=t["hp"],max_hp=t["hp"],mana=t.get("mana",0),max_mana=t.get("mana",0),
        is_hero=t.get("hero",False), height=m.height_at(int(x),int(y)))
    u.radius=t["radius"]; u.uid=len(g.entities)
    g.entities.append(u); return u

def bld(bid, x,y,team=PLAYER, prog=1.0):
    b=BUILDINGS[bid]; e=E(is_building=True,bid=bid,team=team,x=x,y=y,bw=b["size"][0],bh=b["size"][1],
        build_progress=prog,hp=b["hp"],max_hp=b["hp"],height=m.height_at(int(x),int(y)))
    e.uid=len(g.entities); g.entities.append(e); return e

# player base composition
bld("townhall",18,66)
bld("farm",13,70); bld("barracks",23,68); bld("tower",12,66); bld("blacksmith",17,72)
for i,(rig,dx,dy) in enumerate([("hero",24.5,71.5),("footman",23.5,69.5),("footman",25.5,69.5),
                                ("archer",26.5,71.0),("archer",22.5,72.5),("priest",20,72.5),
                                ("knight",27.5,73.0),("knight",20.5,74.0),("ballista",18.5,74.0),
                                ("worker",27.5,68.0),("worker",28.5,69.0),("worker",28.0,70.2)]):
    unit(rig,dx,dy,PLAYER, facing=i%4, anim=("walk" if i%3==0 else "idle"))
# enemy camp near goat path/bottom of ramp
bld("bonetower",54,23,ENEMY); bld("bonetower",67,23,ENEMY); bld("ziggurat",54,8,ENEMY)
for i,(rig,dx,dy) in enumerate([("ghoul",57.5,21.5),("ghoul",64.5,21.5),("fiend",66.5,12.5),
                                ("necromancer",63,19),("abomination",62,23),("hollow-king",61.5,19),
                                ("skeleton",58,20),("skeleton",65,20)]):
    unit(rig,dx,dy,ENEMY,facing=(i+1)%4)

def shot(camxy, path, t=1.2):
    cam=Camera(*r.w2s(camxy[0],camxy[1],1), r.cam_bounds()); cam.clamp()
    screen=pygame.Surface((1600,900))
    for i in range(4): r.draw(screen,g,cam,t+i/60)
    pygame.image.save(screen,path); print("saved",path)

g.entities[0].selected=True
shot((22,69),"design/scene-player.png")
shot((62,21),"design/scene-enemy.png")
shot((14,60),"design/scene-mine.png")
