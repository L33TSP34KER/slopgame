import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy");os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame
from src.flare_units import FlareUnits, AVATARS, ENEMIES
from src.defs import PLAYER, ENEMY
pygame.init(); pygame.display.set_mode((64,64))
u=FlareUnits()
rigs=list(AVATARS)+[r for r in ENEMIES if r in u.enemies]
anims=(("idle",4),("walk",8),("attack",4),("cast",4),("death",6))
# one row per rig/facing, cells anim*maxframes
cw,ch=110,120
W=max(sum(n for _,n in anims)+len(anims)*3,20)*cw
H=len(rigs)*4*ch
S=pygame.Surface((W,H)); S.fill((36,34,42))
font=pygame.font.Font(None,18); small=pygame.font.Font(None,14)
y=0
for rig in rigs:
    team=PLAYER if rig in AVATARS else ENEMY
    for facing in range(4):
        x=0
        lab=f"{rig}  dir{facing}"; S.blit(small.render(lab,True,(230,220,190)),(x+4,y+2)); x+=0
        for anim,n in anims:
            for f in range(n):
                img=u.sprite(rig,facing,anim,f,team)
                if img:
                    im,ax,ay=img
                    im=pygame.transform.smoothscale(im,(int(im.get_width()*1.7),int(im.get_height()*1.7)))
                    ax*=1.7; ay*=1.7
                    S.blit(im,(x+cw//2-int(ax),y+ch-14-int(ay)))
                x+=cw
            x+=24
        y+=ch
pygame.image.save(S,'design/anim-sheet.png'); print('saved',S.get_size())
# focused player sheet at 3x: footman/knight/archer + walk/attack
sel=("footman","knight","archer","hero")
cw,ch=180,190; W=4*4*cw; H=len(sel)*4*ch
S=pygame.Surface((W,H)); S.fill((40,38,46)); y=0
for rig in sel:
    for facing in range(4):
        x=0
        for anim,n in (("idle",4),("walk",8),("attack",4),("death",6)):
            for f in range(n):
                img=u.sprite(rig,facing,anim,f,PLAYER)
                if img:
                    im,ax,ay=img; sc=2.8
                    im=pygame.transform.smoothscale(im,(int(im.get_width()*sc),int(im.get_height()*sc)))
                    S.blit(im,(x+cw//2-int(ax*sc),y+ch-16-int(ay*sc)))
                x+=cw
        y+=ch
pygame.image.save(S,'design/anim-player.png'); print('player',S.get_size())
