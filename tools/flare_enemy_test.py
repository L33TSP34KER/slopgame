import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame; pygame.init(); pygame.display.set_mode((1,1))
def parse(path):
    secs={}; cur=None
    for line in open(path):
        line=line.strip(); m=re.match(r'\[(\w+)\]',line)
        if m: cur=m.group(1); secs[cur]=dict(frames=0,rows={}); continue
        if line.startswith('frames=') and cur: secs[cur]['frames']=int(line.split('=')[1])
        if line.startswith('frame=') and cur:
            v=[int(x) for x in line[6:].split(',')]; secs[cur]['rows'][(v[0],v[1])]=(v[2],v[3],v[4],v[5],v[6],v[7])
    return secs
names=['skeleton','zombie','skeleton_mage','minotaur','antlion','goblin_elite','stealth','skeleton_knight_boss']
S=pygame.Surface((8*170, len(names)*190+40),pygame.SRCALPHA); S.fill((26,24,30))
f=pygame.font.Font(None,22)
for row,n in enumerate(names):
    img=pygame.image.load(f'assets/flare/enemies/{n}.png').convert_alpha(); d=parse(f'assets/flare/enemies/defs/{n}.txt')
    for dir_ in range(8):
        rect=d['stance']['rows'][(0,dir_)]; x,y,w,h,ox,oy=rect
        s=pygame.Surface((128,128),pygame.SRCALPHA)
        s.blit(img,(64+ox-w//2, 96-oy-h),(x,y,w,h))
        s=pygame.transform.smoothscale(s,(128*1.3,128*1.3))
        S.blit(s,(dir_*170, row*190+30)); S.blit(f.render(f'{n} d{dir_}',True,(230,220,200)),(dir_*170+4,row*190+8))
pygame.image.save(S,'design/flare-enemies-test.png'); print('saved')
