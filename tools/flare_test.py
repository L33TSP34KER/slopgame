import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame; pygame.init(); pygame.display.set_mode((1,1))
BASE='assets/flare/units'
def parse(path):
    secs={}; cur=None
    for line in open(path):
        line=line.strip()
        m=re.match(r'\[(\w+)\]',line)
        if m: cur=m.group(1); secs[cur]=dict(frames=0,rows={}); continue
        if line.startswith('frames=') and cur: secs[cur]['frames']=int(line.split('=')[1])
        if line.startswith('frame=') and cur:
            v=[int(x) for x in line[6:].split(',')]
            secs[cur]['rows'][(v[0],v[1])]=(v[2],v[3],v[4],v[5],v[6],v[7])
    return secs
layers=['default_legs','default_feet','default_chest','head_short','chain_cuirass','chain_coif','chain_greaves','chain_boots','chain_gloves','longsword','shield']
imgs={n:pygame.image.load(f'{BASE}/layers/{n}.png').convert_alpha() for n in layers}
defs={n:parse(f'{BASE}/defs/{n}.txt') for n in layers}
def compose(conv):
    s=pygame.Surface((128,128),pygame.SRCALPHA)
    for n in layers:
        sec=defs[n].get('stance'); rect=sec['rows'][(0,0)]; x,y,w,h,ox,oy=rect
        if conv=='A': dx,dy=64+ox-w//2, 96-oy
        elif conv=='B': dx,dy=64+ox-w//2, 96-oy-h
        elif conv=='C': dx,dy=64+ox, 96-oy
        else: dx,dy=64-ox-w//2, 96-oy
        s.blit(imgs[n],(dx,dy),(x,y,w,h))
    return s
S=pygame.Surface((4*128*3+80,128*3+60),pygame.SRCALPHA); S.fill((26,24,30))
f=pygame.font.Font(None,30)
for i,conv in enumerate('ABCD'):
    im=compose(conv); im=pygame.transform.smoothscale(im,(128*3,128*3))
    S.blit(im,(20+i*(128*3+20),40)); S.blit(f.render(conv,True,(240,230,200)),(20+i*(128*3+20),10))
pygame.image.save(S,'design/flare-compose-test.png'); print('saved')
