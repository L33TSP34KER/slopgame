import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame
pygame.init()
pygame.display.set_mode((1600, 900))
from src.mapgen import generate_map
from src.art import Art
from src.render import Renderer, Camera
from src.defs import PLAYER

class G:
    def __init__(self, m, art):
        self.map, self.art = m, art
        self.entities = []
        self.projectiles = []
        self.particles = []
        self.vis = bytearray([1]) * (m.w * m.h)
        self.explored = bytearray([1]) * (m.w * m.h)
        self.selection = []
        self.placement = None
        self.drag_start = self.drag_now = None
        self.attack_move_mode = False
        self.targeting = False
        self.mouse_tile = (20, 68)
        self.mode = "play"
        self.debug = False
        self.fps = 60

m = generate_map()
art = Art()
g = G(m, art)
r = Renderer(g)
cam = Camera(*r.w2s(24, 69, 1), r.cam_bounds())
cam.clamp()
screen = pygame.Surface((1600, 900))
for i in range(30):
    r.draw(screen, g, cam, i / 30.0)
pygame.image.save(screen, "design/render-test.png")
print("saved render-test.png")
# also a wide shot at the enemy base
cam2 = Camera(*r.w2s(62, 22, 2), r.cam_bounds()); cam2.clamp()
for i in range(3):
    r.draw(screen, g, cam2, 1.0 + i / 30)
pygame.image.save(screen, "design/render-test-enemy.png")
print("saved render-test-enemy.png")
