import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy"); os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame; pygame.init(); pygame.display.set_mode((1, 1))
from src.mapgen import generate_map
from src.world import World
from src.ai import EnemyAI
from src.defs import *

class Dummy:
    sfx = None
    def shake(self, *a): pass
    def on_mission_end(self, r): print("MISSION END", r)

m = generate_map()
w = World(Dummy(), m, None, "knight")
w.ai = EnemyAI(w)
w.started = True
print("start: entities", len(w.entities), "gold", w.gold, "lumber", w.lumber,
      "food", w.food_used(PLAYER), "/", w.food_max(PLAYER))
hero = w.hero
workers = [u for u in w.units_of(PLAYER) if u.worker]
mine = next(x for x in m.mines if x["owned"] if False) if False else next(x for x in m.mines if not x["neutral"])
w.cmd_gather(workers, {"type": "gold", "mine": mine})
# build a farm next to the hall
farm_pos = None
for yy in range(62, 74):
    for xx in range(10, 16):
        if w.can_place("farm", xx, yy):
            farm_pos = (xx, yy); break
    if farm_pos: break
print("farm pos", farm_pos)
b = w.cmd_build([workers[0]], "farm", *farm_pos) if farm_pos else None
step = 1/30
t0 = time.time()
for i in range(int(70 / step)):
    w.update(step)
    if i % (30 * 10) == 0:
        print(f"t={w.time:5.1f} ents={len(w.entities):3d} gold={w.gold:4.0f} lumber={w.lumber:3.0f} "
              f"farm={b.build_progress if b else 0:.2f} enemies={len(w.units_of(ENEMY))} state={w.state}")
    if w.state != "playing": break
print("elapsed", round(time.time()-t0,2), "state", w.state, "kills", w.stats)
# train a worker then a barracks?
hall = next(x for x in w.buildings_of(PLAYER) if x.bid == "townhall")
w.cmd_train(hall, "worker")
for i in range(int(20/step)): w.update(step)
print("units", len(w.units_of(PLAYER)), "workers", len([u for u in w.units_of(PLAYER) if u.worker]),
      "gold", w.gold, "lumber", w.lumber)
# issue an attack move toward enemy base
army = [u for u in w.units_of(PLAYER) if not u.worker]
if army:
    w.cmd_attack_move(army, 50, 30)
    for i in range(int(30/step)): w.update(step)
print("after push: player units", len(w.units_of(PLAYER)), "enemy units", len(w.units_of(ENEMY)),
      "player buildings", len(w.buildings_of(PLAYER)), "state", w.state)
print("nav sanity: hero", (round(hero.x,1), round(hero.y,1)) if hero else None)
print("fog visible", sum(w.vis), "explored", sum(w.explored))
