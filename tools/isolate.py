import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame;pygame.init();pygame.display.set_mode((1600,900))
from src.mapgen import generate_map
from src.world import World
from src.art import Art
from src.render import Renderer, Camera
from src.defs import *
class D:
    sfx=None
    def shake(self,*a):pass
    def on_mission_end(self,r):pass
m=generate_map();art=Art();w=World(D(),m,art,"knight");w.started=True
w.mode='play'
for i in range(len(w.vis)): w.explored[i]=1; w.vis[i]=1
r=Renderer(w); cam=Camera(*r.w2s(61,45,1), r.cam_bounds()); cam.clamp()
scr=pygame.Surface((1600,900))
def shot(name, no_water=False, no_fog=False):
    ow=r._draw_water
    if no_water: r._draw_water=lambda *a:None
    if no_fog: r._draw_fog=lambda *a:None
    for k in range(3): r.draw(scr,w,cam,1.0)
    pygame.image.save(scr,'design/iso-'+name+'.png')
    r._draw_water=ow
    print('saved',name)
shot('base')
shot('nowater',no_water=True)
shot('nofog',no_fog=True)
print('alerts',w._alerts)
