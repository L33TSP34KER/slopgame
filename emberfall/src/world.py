"""Emberfall simulation: units, buildings, economy, combat, hero, fog, mission."""
from __future__ import annotations
import math, random
from .core import (clamp, dist, dist2, angle_lerp, approach, SpatialHash, fmt_time, Rng)
from .defs import *
from .pathfind import find_path, walkable, nearest_walkable, line_clear
from . import mapgen as MG

ARATE = dict(idle=3.0, walk=9.0, attack=8.0, cast=5.0, death=5.0, gather=7.0)
ANIM_LEN = dict(idle=1.0, walk=1.0, attack=1.0, cast=1.0, death=1.0, gather=1.0)


class Entity:
    __slots__ = (
        "uid", "kind", "team", "x", "y", "height", "hp", "max_hp", "mana", "max_mana",
        "armor", "armor_type", "damage_type", "dmg_min", "dmg_max", "range", "cooldown",
        "attack_cd", "speed", "sight", "food", "radius", "alive", "death_t", "selected",
        "facing", "facing_bucket", "anim", "anim_t", "order", "path", "path_i", "repath_t",
        "target", "carry", "carry_type", "node", "gather_t", "build_target", "repair",
        "queue", "rally", "is_building", "bid", "bw", "bh", "build_progress", "builders",
        "is_hero", "level", "xp", "abil_cd", "shield_hp", "shield_t", "stun", "slow_t",
        "slow_amt", "summon_t", "scan_t", "home", "bounty", "xp_value", "blocked_tiles",
        "research", "research_t", "owner", "anim_speed", "scale", "summon_life", "boss",
        "attack_anim", "ranged", "heal", "rig", "slow_hit", "worker", "hero_revive_t", "poison",
        "last_sfx", "stuck_t", "last_pos", "camp", "eff_speed", "path_fail", "alert_ready", "evade"
    )

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, None)
        self.selected = False
        self.alive = True
        self.death_t = 0.0
        self.anim = "idle"
        self.anim_t = 0.0
        self.path = None
        self.path_i = 0
        self.repath_t = 0.0
        self.carry = 0
        self.carry_type = None
        self.queue = []
        self.rally = None
        self.is_building = False
        self.build_progress = 1.0
        self.builders = 0
        self.is_hero = False
        self.level = 1
        self.xp = 0
        self.abil_cd = {}
        self.shield_hp = 0.0
        self.shield_t = 0.0
        self.stun = 0.0
        self.slow_t = 0.0
        self.slow_amt = 0.0
        self.summon_t = 0.0
        self.scan_t = 0.0
        self.stuck_t = 0.0
        self.last_pos = None
        self.facing = math.pi / 2
        self.facing_bucket = 2
        self.attack_cd = 0.0
        self.attack_anim = "attack"
        self.research = None
        self.research_t = 0.0
        self.hero_revive_t = 0.0
        for k, v in kw.items():
            setattr(self, k, v)


class World:
    def __init__(self, game, map_obj, art, difficulty="knight", seed=7):
        self.game = game
        self.map = map_obj
        self.art = art
        self.diff = DIFFICULTY[difficulty]
        self.diff_id = difficulty
        self.rng = Rng(seed)
        self.time = 0.0
        self.mode = "play"
        self.paused = False
        self.entities = []
        self.projectiles = []
        self.particles = []
        self.uid = 0
        self.grid = SpatialHash(3)
        self.blocked = set()
        self.vis = bytearray(map_obj.w * map_obj.h)
        self.explored = bytearray(map_obj.w * map_obj.h)
        self.fog_t = 0.0
        self.gold = 800
        self.lumber = 220
        self.upgrades = set()
        self.dmg_bonus = 0
        self.armor_bonus = 0
        self.hero = None
        self.stats = dict(kills=0, losses=0, gold_gathered=0, lumber_gathered=0,
                          units_trained=0, buildings_raised=0, damage=0, abilities=0)
        self.events = []
        self.state = "playing"
        self.end_t = 0.0
        self.wave_index = 0
        self.wave_t = 120.0
        self.next_wave = 240.0
        self.announced = {}
        self.mouse_tile = (24, 70)
        self.placement = None
        self.drag_start = self.drag_now = None
        self.attack_move_mode = False
        self.targeting = None
        self.debug = False
        self.fps = 60
        self.cam_hint = (24, 69)
        self.night = 0.0
        self.started = False
        self.weather_t = 0.0
        self.last_selection = []
        self.control_groups = {}
        self.sfx = getattr(game, "sfx", None)
        self.ai = None
        self._alerts = []
        self.camp_cleared = set()
        self.mission = dict(main=OBJECTIVE_MAIN, bonus=OBJECTIVE_BONUS, hint="")
        self._spawn_start()

    # ------------------------------------------------------------------ setup
    def _spawn_start(self):
        for side in (PLAYER, ENEMY):
            st = self.map.starts[side]
            for b in st["buildings"]:
                self.spawn_building(b["type"], b["x"], b["y"], side, complete=True,
                                    progress=1.0)
            for (kind, x, y) in st["units"]:
                u = self.spawn_unit(kind, x, y, side)
                if kind == "hero":
                    self.hero = u
        for camp in self.map.camps:
            for c in camp["units"]:
                u = self.spawn_unit(c["type"], c["x"], c["y"], NEUTRAL)
                u.home = (camp["x"], camp["y"])
                u.camp = camp["name"]
        self.update_fog(force=True)
        self._build_grid()

    def spawn_unit(self, kind, x, y, team):
        d = UNITS[kind]
        e = Entity(uid=self._next_uid(), kind=kind, rig=d.get("rig", kind), team=team, x=float(x), y=float(y),
                   height=self.map.height_at(int(x), int(y)), hp=d["hp"], max_hp=d["hp"],
                   mana=d.get("mana", 0), max_mana=d.get("mana", 0), armor=d["armor"],
                   armor_type=d["armor_type"], damage_type=d["damage_type"],
                   dmg_min=d["dmg"][0], dmg_max=d["dmg"][1], range=d["range"],
                   cooldown=d["cooldown"], speed=d["speed"], sight=d["sight"],
                   food=d.get("food", 0), radius=d.get("radius", 0.34),
                   bounty=d.get("bounty", 0), xp_value=d.get("xp", 0),
                   facing=math.pi / 2, facing_bucket=2, attack_cd=self.rng.uniform(0, 0.6),
                   ranged=bool(d.get("projectile")), worker=d.get("worker", False),
                   is_hero=d.get("hero", False), boss=d.get("boss", False),
                   heal=d.get("heal", 0), slow_hit=d.get("slow_hit", 0),
                   summon_life=d.get("duration", 0), scale=d.get("scale", 1.0))
        if team == ENEMY:
            e.hp = int(e.hp * self.diff["hp"])
            e.max_hp = e.hp
            e.dmg_min = int(e.dmg_min * self.diff["dmg"])
            e.dmg_max = int(e.dmg_max * self.diff["dmg"])
        e.anim_speed = 1.0
        e.eff_speed = d["speed"]
        self.entities.append(e)
        return e

    def spawn_building(self, bid, x, y, team, complete=True, progress=None):
        d = BUILDINGS[bid]
        bw, bh = d["size"]
        e = Entity(uid=self._next_uid(), kind=bid, bid=bid, team=team, x=float(x), y=float(y),
                   bw=bw, bh=bh, height=self.map.height_at(int(x), int(y)),
                   hp=d["hp"], max_hp=d["hp"], armor=d["armor"], armor_type=d["armor_type"],
                   damage_type="normal", dmg_min=0, dmg_max=0, range=0, cooldown=0,
                   speed=0, sight=d.get("sight", 7), food=d.get("food", 0),
                   radius=max(bw, bh) * 0.5, is_building=True, build_progress=1.0 if complete else 0.0,
                   queue=[], blocked_tiles=[])
        e.attack_cd = 0.0
        if d.get("attack"):
            a = d["attack"]
            e.dmg_min, e.dmg_max = a["dmg"]
            e.range, e.cooldown, e.damage_type = a["range"], a["cooldown"], a["type"]
            e.ranged = True
        if not complete:
            p = progress if progress is not None else 0.0
            e.build_progress = p
            e.hp = max(1, int(e.max_hp * max(0.1, p)))
        for yy in range(y, y + bh):
            for xx in range(x, x + bw):
                if self.map.inb(xx, yy):
                    self.blocked.add((xx, yy))
                    e.blocked_tiles.append((xx, yy))
        self.entities.append(e)
        return e

    def _next_uid(self):
        self.uid += 1
        return self.uid

    # ------------------------------------------------------------------ queries
    def _build_grid(self):
        self.grid.clear()
        for e in self.entities:
            if e.alive:
                r = max(e.radius, 0.6) if not e.is_building else max(e.bw, e.bh) * 0.5
                self.grid.insert(e, e.x, e.y, r)

    def units_of(self, team):
        return [e for e in self.entities if e.alive and not e.is_building and e.team == team]

    def buildings_of(self, team):
        return [e for e in self.entities if e.alive and e.is_building and e.team == team]

    def enemies_near(self, e, radius, include_buildings=True):
        out = []
        for o in self.grid.query(e.x, e.y, radius):
            if not o.alive or o.team == e.team or o.team == NEUTRAL and e.team == NEUTRAL:
                continue
            if o.team == NEUTRAL and e.team != NEUTRAL:
                pass
            if not include_buildings and o.is_building:
                continue
            if dist(e.x, e.y, o.x, o.y) <= radius + (max(o.bw, o.bh) * 0.3 if o.is_building else 0):
                out.append(o)
        return out

    def nearest_enemy(self, e, radius, team=None):
        best, bd = None, radius
        for o in self.enemies_near(e, radius):
            if team is not None and o.team != team:
                continue
            d = dist(e.x, e.y, o.x, o.y) - (0.5 if not o.is_building else 0)
            if d < bd:
                best, bd = o, d
        return best

    def dropoff_for(self, u):
        best, bd = None, 1e9
        for b in self.buildings_of(PLAYER):
            if BUILDINGS[b.bid].get("dropoff"):
                d = dist(u.x, u.y, b.x + b.bw / 2, b.y + b.bh / 2)
                if d < bd:
                    best, bd = b, d
        return best

    def food_max(self, team):
        return sum(BUILDINGS[b.bid].get("food", 0) for b in self.buildings_of(team)
                   if b.build_progress >= 1)

    def food_used(self, team):
        return sum(u.food for u in self.units_of(team) if not u.is_building)

    def tile_of(self, e):
        return (int(e.x), int(e.y))

    # ------------------------------------------------------------------ fog
    def update_fog(self, force=False):
        m = self.map
        self.vis = bytearray(m.w * m.h)
        for e in self.entities:
            if not e.alive or e.team != PLAYER:
                continue
            r = e.sight + (1.5 if e.is_building else 0)
            x0, x1 = max(0, int(e.x - r)), min(m.w - 1, int(e.x + r))
            y0, y1 = max(0, int(e.y - r)), min(m.h - 1, int(e.y + r))
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    if (x - e.x) ** 2 + (y - e.y) ** 2 <= r * r:
                        i = y * m.w + x
                        self.vis[i] = 1
                        self.explored[i] = 1
        self.fog_t = 0.0

    # ------------------------------------------------------------------ orders
    def cmd_stop(self, units):
        for u in units:
            u.order = None
            u.path = None
            u.target = None
            u.anim = "idle"
        self.play("command")

    def cmd_hold(self, units):
        for u in units:
            u.order = {"type": "hold"}
            u.path = None
            u.target = None
        self.play("command")

    def cmd_move(self, units, x, y, attack_move=False):
        units = [u for u in units if u.alive and not u.is_building]
        if not units:
            return
        n = len(units)
        cols = max(1, int(math.ceil(math.sqrt(n))))
        for k, u in enumerate(units):
            ring = k // 9
            slot = k % 9
            ox = (slot % 3 - 1) * 0.85 + (ring * 0.4 if ring else 0)
            oy = (slot // 3 - 1) * 0.85 + (ring * 0.4 if ring else 0)
            tx, ty = x + ox, y + oy
            if not walkable(self.map, int(tx), int(ty), self.blocked):
                tx, ty = x, y
            u.order = {"type": "attack_move" if attack_move else "move", "x": tx, "y": ty}
            u.target = None
            self._set_path(u, (tx, ty))
        self.play("command")

    def cmd_attack(self, units, target):
        for u in units:
            if u.alive and not u.is_building and target and target.alive:
                u.order = {"type": "attack", "target": target}
                u.path = None
        self.play("command")

    def cmd_attack_move(self, units, x, y):
        self.cmd_move(units, x, y, attack_move=True)

    def cmd_gather(self, units, node):
        workers = [u for u in units if u.alive and not u.is_building and u.worker]
        for u in workers:
            u.order = {"type": "gather", "node": node, "phase": "to"}
            u.node = node
            u.path = None
            u.gather_t = 0
            u.target = None
        if workers:
            self.play("command")

    def nearest_node(self, u, kind=None, radius=18):
        best, bd = None, radius
        for mine in self.map.mines:
            if mine["gold"] <= 0:
                continue
            if kind and kind != "gold":
                continue
            d = math.hypot(u.x - mine["x"], u.y - mine["y"])
            if d < bd:
                best, bd = {"type": "gold", "mine": mine}, d
        if kind in (None, "wood"):
            for (tx, ty), wood in self.map.wood.items():
                if wood <= 0:
                    continue
                d = math.hypot(u.x - tx - 0.5, u.y - ty - 0.5)
                if d < bd:
                    best, bd = {"type": "wood", "x": tx, "y": ty}, d
        return best

    def node_pos(self, node):
        if not node:
            return None
        if node["type"] == "gold":
            m = node["mine"]
            return (m["x"] - 0.5, m["y"] - 0.5, 2, 2)
        return (node["x"], node["y"], 1, 1)

    def node_depleted(self, node):
        if not node:
            return True
        if node["type"] == "gold":
            return node["mine"]["gold"] <= 0
        return self.map.wood.get((node["x"], node["y"]), 0) <= 0

    def cmd_build(self, units, bid, x, y):
        workers = [u for u in units if u.alive and u.worker]
        if not workers or not self.can_place(bid, x, y):
            return None
        d = BUILDINGS[bid]
        req = d.get("requires")
        if req and not any(b.bid == req and b.build_progress >= 1 for b in self.buildings_of(PLAYER)):
            self.alert("Requires " + BUILDINGS[req]["name"] + ".")
            self.play("error")
            return None
        if not self.pay(d["cost"]):
            self.alert("Not enough resources.")
            self.play("error")
            return None
        b = self.spawn_building(bid, x, y, PLAYER, complete=False, progress=0.0)
        for u in workers:
            self.order_build(u, b)
        self.stats["buildings_raised"] += 1
        self.play("build")
        return b

    def order_build(self, u, b, repair=False):
        u.order = {"type": "build", "target": b, "repair": repair}
        u.build_target = b
        u.path = None
        u.target = None

    def placement_valid(self, x, y):
        if not self.placement:
            return False
        return self.can_place(self.placement["bid"], x, y)

    def can_place(self, bid, x, y):
        d = BUILDINGS[bid]
        bw, bh = d["size"]
        m = self.map
        h = None
        for yy in range(y, y + bh):
            for xx in range(x, x + bw):
                if not m.inb(xx, yy):
                    return False
                i = yy * m.w + xx
                if m.terrain[i] == 3 or m.blocked[i] or (xx, yy) in self.blocked:
                    return False
                if xx < 2 or yy < 2 or xx >= m.w - 2 or yy >= m.h - 2:
                    return False
                hh = m.height[i]
                if h is None:
                    h = hh
                elif hh != h:
                    return False
        for u in self.entities:
            if u.alive and not u.is_building and x - 0.5 <= u.x <= x + bw + 0.5 and y - 0.5 <= u.y <= y + bh + 0.5:
                return False
        return True

    def pay(self, cost, team=PLAYER):
        if team == PLAYER:
            g, l = cost.get("g", 0), cost.get("l", 0)
            if self.gold < g or self.lumber < l:
                return False
            self.gold -= g
            self.lumber -= l
            return True
        return True

    def refund(self, cost, team=PLAYER):
        if team == PLAYER:
            self.gold += cost.get("g", 0)
            self.lumber += cost.get("l", 0)

    def cmd_train(self, b, utype):
        if not b or not b.alive or not b.is_building:
            return
        d = UNITS[utype]
        if len(b.queue) >= 5:
            self.alert("The training queue is full.")
            self.play("error")
            return
        if utype == "knight" and not any(x.bid == "keep" and x.build_progress >= 1 for x in self.buildings_of(PLAYER)):
            self.alert("A Keep is required.")
            self.play("error")
            return
        cap = self.food_max(PLAYER)
        used = self.food_used(PLAYER) + sum(UNITS[q["type"]]["food"] for q in b.queue)
        if used + d["food"] > cap:
            self.alert("Not enough food. Build more farms.")
            self.play("error")
            return
        if not self.pay(d["cost"]):
            self.alert("Not enough resources.")
            self.play("error")
            return
        b.queue.append({"type": utype, "progress": 0.0, "time": d["build_time"], "cost": d["cost"]})
        self.play("click")

    def cmd_cancel_queue(self, b):
        if b and b.queue:
            q = b.queue.pop()
            self.refund(q["cost"])
            self.play("click")

    def cmd_research(self, b, uid):
        if not b or uid in self.upgrades or (b.research and b.research["id"] == uid):
            return
        u = UPGRADES[uid]
        req = u.get("req_upgrade")
        if req and req not in self.upgrades:
            self.alert("Requires " + UPGRADES[req]["name"] + ".")
            self.play("error")
            return
        if b.research:
            self.alert("Already researching.")
            return
        if not self.pay(u["cost"]):
            self.alert("Not enough resources.")
            self.play("error")
            return
        b.research = {"id": uid, "t": 0.0}
        self.play("click")

    def cmd_rally(self, b, x, y):
        if b:
            b.rally = (x, y)
            self.play("click")

    def cmd_cast(self, hero, aid, target=None):
        if not hero or not hero.alive or not hero.is_hero:
            return
        a = ABILITIES[aid]
        if hero.level < a["unlock"]:
            self.alert("Ability not yet unlocked.")
            self.play("error")
            return
        if hero.abil_cd.get(aid, 0) > 0:
            self.alert("Ability is cooling down.")
            self.play("error")
            return
        if hero.mana < a["mana"]:
            self.alert("Not enough mana.")
            self.play("error")
            return
        lv = hero.level
        if a["target"] == "unit":
            if not target or not target.alive or target.team == PLAYER or dist(hero.x, hero.y, target.x, target.y) > a["range"]:
                self.alert("Invalid target.")
                self.play("error")
                return
            self.damage(target, a["dmg"](lv), hero, "magic")
            target.stun = max(target.stun, a["stun"])
            self.burst(target.x, target.y, (255, 150, 70), 14, 1.2)
        elif a["target"] == "self":
            hero.shield_hp = a["shield"](lv)
            hero.shield_t = a["duration"]
            self.burst(hero.x, hero.y, (255, 190, 100), 14, 1.0)
        else:
            tx, ty = target if target else (hero.x, hero.y)
            if dist(hero.x, hero.y, tx, ty) > a["range"]:
                return
            for e in list(self.entities):
                if not e.alive:
                    continue
                d = dist(tx, ty, e.x, e.y)
                if e.team != PLAYER and d <= a["radius"]:
                    self.damage(e, a["dmg"](lv), hero, "magic")
                    if a.get("stun"):
                        e.stun = max(e.stun, a["stun"])
                elif e.team == PLAYER and not e.is_building and d <= a["radius"]:
                    e.hp = min(e.max_hp, e.hp + a["heal"](lv))
            self.burst(tx, ty, (255, 214, 140) if aid == "daybreak" else (255, 150, 70),
                       26 if aid == "daybreak" else 16, 1.6)
        hero.mana -= a["mana"]
        hero.abil_cd[aid] = a["cooldown"]
        hero.anim = "cast"
        hero.anim_t = 0.0
        self.stats["abilities"] += 1
        self.play("magic")
        if self.game and hasattr(self.game, "shake"):
            self.game.shake(4 if aid != "daybreak" else 10, 0.3)

    # ------------------------------------------------------------------ update
    def update(self, dt):
        if self.paused or self.mode != "play":
            return
        self.time += dt
        self.night = 0.5 + 0.5 * math.sin(self.time * 0.012 - 1.2)
        self._alert_tick(dt)
        for u in list(self.entities):
            if not u.alive:
                u.death_t += dt
                if u.death_t > 6.0:
                    try:
                        self.entities.remove(u)
                    except ValueError:
                        pass
                continue
            u.anim_t += dt
            if u.stun > 0:
                u.stun -= dt
                continue
            if u.shield_t > 0:
                u.shield_t -= dt
                if u.shield_t <= 0:
                    u.shield_hp = 0
            if u.slow_t > 0:
                u.slow_t -= dt
            if u.is_building:
                self.update_building(u, dt)
            else:
                self.update_unit(u, dt)
                if u.alive and u.order is None and (int(self.time * 30) + u.uid) % 2 == 0:
                    self._separate(u)
        self.update_projectiles(dt)
        self.update_particles(dt)
        self.fog_t += dt
        if self.fog_t > 0.25:
            self.update_fog()
        if self.ai:
            self.ai.update(dt)
        self.update_mission(dt)
        self._build_grid()

    def _separate(self, u):
        for o in self.grid.query(u.x, u.y, 1.1):
            if o is u or not o.alive or o.is_building or o.team != u.team:
                continue
            d = dist(u.x, u.y, o.x, o.y)
            need = (u.radius + o.radius) * 0.85
            if 0.001 < d < need:
                push = (need - d) * 0.9
                nx = u.x + (u.x - o.x) / d * push
                ny = u.y + (u.y - o.y) / d * push
                if self._passable(nx, ny, u):
                    u.x, u.y = nx, ny

    def update_unit(self, u, dt):
        # mana
        if u.max_mana:
            u.mana = min(u.max_mana, u.mana + dt * 2.2)
        for k in list(u.abil_cd):
            u.abil_cd[k] = max(0.0, u.abil_cd[k] - dt)
        if u.attack_cd > 0:
            u.attack_cd -= dt
        if u.summon_life and self.time > u.summon_life:
            self.kill(u, None)
            return
        if u.slow_t > 0:
            u.eff_speed = u.speed * (1 - u.slow_amt)
        else:
            u.eff_speed = u.speed
        o = u.order
        if u.heal and u.team == PLAYER:
            if self.try_heal(u):
                return
        if o is None:
            if self.auto_acquire(u, aggro=(not u.worker) or u.team != PLAYER):
                return
            u.anim = "idle"
            return
        t = o["type"]
        if t == "move":
            if not u.path and o.get("x") is not None:
                self._set_path(u, (o["x"], o["y"]))
            if self.follow_path(u, dt):
                u.order = None
                u.anim = "idle"
            else:
                u.anim = "walk"
        elif t == "attack_move":
            tgt = self.nearest_enemy(u, u.sight, team=PLAYER if u.team == ENEMY else ENEMY)
            if tgt:
                self.engage(u, tgt, dt, leash=10)
            elif not u.path and o.get("x") is not None:
                self._set_path(u, (o["x"], o["y"]))
                self.follow_path(u, dt)
                u.anim = "walk"
            elif self.follow_path(u, dt):
                u.order = None
                u.anim = "idle"
            else:
                u.anim = "walk"
        elif t == "attack":
            tgt = o.get("target")
            if not tgt or not tgt.alive:
                tgt = self.nearest_enemy(u, u.sight + 2)
                o["target"] = tgt
            if not tgt:
                u.order = None
                return
            self.engage(u, tgt, dt)
        elif t == "gather":
            self.update_gather(u, dt)
        elif t == "build":
            self.update_build_order(u, dt)
        elif t == "hold":
            self.auto_acquire(u, aggro=True)
            if u.anim not in ("attack", "cast", "gather"):
                u.anim = "idle"
        elif t == "return":
            self.update_return(u, dt)
        else:
            u.anim = "idle"

    def _set_path(self, u, goal):
        start = (u.x, u.y)
        path = find_path(self.map, start, goal, extra=self.blocked)
        if path:
            u.path = path
            u.path_i = 0
            u.repath_t = 0
        else:
            u.path = None
            u.path_fail = True

    def follow_path(self, u, dt):
        if not u.path:
            return True
        spd = getattr(u, "eff_speed", u.speed)
        left = spd * dt
        steps = 0
        while left > 0 and u.path and u.path_i < len(u.path):
            tx, ty = u.path[u.path_i]
            d = dist(u.x, u.y, tx, ty)
            if d < 0.12:
                u.path_i += 1
                continue
            move = min(left, d)
            dx, dy = (tx - u.x) / (d or 1), (ty - u.y) / (d or 1)
            # separation
            for o in self.grid.query(u.x, u.y, 1.0):
                if o is u or not o.alive or o.is_building or o.team != u.team:
                    continue
                dd = dist(u.x, u.y, o.x, o.y)
                if 0.001 < dd < (u.radius + o.radius) * 0.95:
                    push = ((u.radius + o.radius) * 0.95 - dd) * 0.5
                    dx += (u.x - o.x) / dd * push * 1.5
                    dy += (u.y - o.y) / dd * push * 1.5
            mag = math.hypot(dx, dy) or 1
            nx = u.x + dx / mag * move
            ny = u.y + dy / mag * move
            # do not step into blocked tiles
            if self._passable(nx, ny, u):
                u.x, u.y = nx, ny
                target_angle = math.atan2(dy, dx)
                u.facing = angle_lerp(u.facing, target_angle, 0.35)
                self._set_bucket(u)
            else:
                u.stuck_t += dt
                if u.stuck_t > 0.6:
                    u.stuck_t = 0
                    self._set_path(u, u.path[-1] if u.path else (u.x, u.y))
                    return False
            left -= move
            if d < 0.2:
                u.path_i += 1
            steps += 1
            if steps > 8:
                break
        if u.path_i >= len(u.path):
            u.path = None
            u.height = self.map.height_at(int(u.x), int(u.y))
            return True
        return False

    def _passable(self, x, y, u):
        tx, ty = int(x), int(y)
        if not self.map.inb(tx, ty):
            return False
        i = ty * self.map.w + tx
        if self.map.terrain[i] == 3 or self.map.blocked[i]:
            return False
        if (tx, ty) in self.blocked:
            # allow if already inside a blocked tile (spawn/edge)
            return (int(u.x), int(u.y)) == (tx, ty)
        return True

    def _set_bucket(self, u):
        a = u.facing
        sdx = math.cos(a) - math.sin(a)
        sdy = (math.cos(a) + math.sin(a)) * 0.5
        if sdy >= 0:
            u.facing_bucket = 0 if sdx >= 0 else 2
        else:
            u.facing_bucket = 1 if sdx >= 0 else 3

    def face_to(self, u, tx, ty):
        a = math.atan2(ty - u.y, tx - u.x)
        u.facing = angle_lerp(u.facing, a, 0.5)
        self._set_bucket(u)

    def engage(self, u, tgt, dt, leash=None):
        if not tgt or not tgt.alive:
            u.order = None
            return
        tx = tgt.x + (tgt.bw / 2 if tgt.is_building else 0)
        ty = tgt.y + (tgt.bh / 2 if tgt.is_building else 0)
        d = dist(u.x, u.y, tx, ty) - (max(tgt.bw, tgt.bh) * 0.3 if tgt.is_building else 0)
        self.face_to(u, tx, ty)
        if d <= u.range + 0.2:
            u.path = None
            u.anim = u.attack_anim
            if u.attack_cd <= 0:
                u.attack_cd = u.cooldown
                u.anim_t = 0.0
                self.perform_attack(u, tgt)
        else:
            u.anim = "walk"
            if not u.path or u.path_i >= len(u.path) or u.repath_t <= 0:
                near = nearest_walkable(self.map, int(tx), int(ty), self.blocked, 4)
                if near:
                    self._set_path(u, near)
                u.repath_t = 0.5
            u.repath_t -= dt
            self.follow_path(u, dt)

    def perform_attack(self, u, tgt):
        if u.ranged and u.range > 2:
            ptype = "arrow" if u.kind == "archer" else "frost" if u.kind == "revenant" else \
                    "shadow" if u.kind == "necromancer" else "bolt" if u.kind in ("fiend", "bonetower") else "holy" if u.kind == "priest" else "arrow"
            self.spawn_projectile(u, tgt, ptype)
        else:
            dmg = self.rng.uniform(u.dmg_min, u.dmg_max)
            self.damage(tgt, dmg, u, u.damage_type)
            self.hit_fx(tgt)
            self.play("sword")
        if getattr(u, "slow_hit", 0) and tgt and tgt.alive:
            tgt.slow_t = 2.0
            tgt.slow_amt = u.slow_hit

    def auto_acquire(self, u, aggro=False):
        if u.team == NEUTRAL and self.time < 0:
            return False
        if u.summon_life:
            return False
        u.scan_t -= 0.1
        if u.scan_t > 0:
            return False
        u.scan_t = 0.35
        r = u.sight if aggro else max(2.2, u.range + 1.5)
        tgt = self.nearest_enemy(u, r)
        if tgt:
            u.order = {"type": "attack", "target": tgt}
            return True
        return False

    def try_heal(self, u):
        if u.attack_cd > 0:
            return False
        for o in self.grid.query(u.x, u.y, u.range + 1):
            if o.team == PLAYER and not o.is_building and o.alive and o.hp < o.max_hp * 0.85 and o is not u:
                if dist(u.x, u.y, o.x, o.y) <= u.range:
                    u.attack_cd = u.cooldown
                    u.anim = "cast"
                    u.anim_t = 0.0
                    self.face_to(u, o.x, o.y)
                    o.hp = min(o.max_hp, o.hp + u.heal)
                    self.burst(o.x, o.y, (255, 220, 140), 6, 0.7)
                    self.play("holy")
                    return True
        return False

    # ------------------------------------------------------------------ gather/build
    def update_gather(self, u, dt):
        o = u.order
        node = o.get("node")
        if self.node_depleted(node):
            node = self.nearest_node(u)
            if not node:
                u.order = None
                u.anim = "idle"
                return
            o["node"] = node
        if u.carry >= 10:
            drop = self.dropoff_for(u)
            if not drop:
                u.anim = "idle"
                return
            cx, cy = drop.x + drop.bw / 2, drop.y + drop.bh / 2
            if dist(u.x, u.y, cx, cy) < max(drop.bw, drop.bh) * 0.8 + 1.2:
                if u.carry_type == "gold":
                    self.gold += u.carry
                    self.stats["gold_gathered"] += u.carry
                    self.play("gold")
                else:
                    self.lumber += u.carry
                    self.stats["lumber_gathered"] += u.carry
                    self.play("chop")
                u.carry = 0
                u.carry_type = None
                u.order = {"type": "gather", "node": node, "phase": "to"}
                u.path = None
            else:
                if not u.path or u.path_i >= len(u.path) or u.repath_t <= 0:
                    near = self.node_adjacent(u, drop.x, drop.y, drop.bw, drop.bh)
                    if near:
                        self._set_path(u, near)
                    u.repath_t = 0.7
                u.repath_t -= dt
                self.follow_path(u, dt)
                u.anim = "walk"
            return
        x, y, w, h = self.node_pos(node)
        if node["type"] == "gold":
            cx, cy = node["mine"]["x"] - 0.5, node["mine"]["y"] - 0.5
        else:
            cx, cy = node["x"] + 0.5, node["y"] + 0.5
        d = dist(u.x, u.y, cx, cy)
        if d < 2.25:
            u.path = None
            u.anim = "gather"
            u.gather_t += dt
            self.face_to(u, cx, cy)
            if u.gather_t >= 1.1:
                u.gather_t = 0
                if node["type"] == "gold":
                    take = min(10, node["mine"]["gold"])
                    node["mine"]["gold"] -= take
                    u.carry = take
                    u.carry_type = "gold"
                else:
                    take = min(10, self.map.wood.get((node["x"], node["y"]), 0))
                    self.map.wood[(node["x"], node["y"])] = max(0, self.map.wood.get((node["x"], node["y"]), 0) - take)
                    u.carry = take
                    u.carry_type = "wood"
                    if self.map.wood[(node["x"], node["y"])] <= 0:
                        self.remove_tree(node["x"], node["y"])
                u.order = {"type": "gather", "node": node, "phase": "back"}
                u.path = None
        else:
            if not u.path or u.path_i >= len(u.path) or u.repath_t <= 0:
                near = self.node_adjacent(u, cx, cy, 1, 1)
                if near:
                    self._set_path(u, near)
                u.repath_t = 0.8
            u.repath_t -= dt
            self.follow_path(u, dt)
            u.anim = "walk"

    def node_adjacent(self, u, cx, cy, w, h):
        best, bd = None, 1e9
        for r in range(1, 4):
            for yy in range(int(cy) - r, int(cy) + r + 1):
                for xx in range(int(cx) - r, int(cx) + r + 1):
                    if not self.map.inb(xx, yy):
                        continue
                    if not walkable(self.map, xx, yy, self.blocked):
                        continue
                    d = math.hypot(xx + 0.5 - cx, yy + 0.5 - cy)
                    if d < bd:
                        best, bd = (xx + 0.5, yy + 0.5), d
        return best

    def remove_tree(self, x, y):
        i = y * self.map.w + x
        self.map.blocked[i] = 0
        for p in self.map.tree_props.get((x, y), []):
            p["gone"] = True
        self.map.wood.pop((x, y), None)

    def update_build_order(self, u, dt):
        b = u.order.get("target") if u.order else None
        if not b or not b.alive:
            u.order = None
            u.anim = "idle"
            return
        if b.build_progress >= 1 and not u.order.get("repair"):
            u.order = None
            u.anim = "idle"
            return
        cx, cy = b.x + b.bw / 2, b.y + b.bh / 2
        if dist(u.x, u.y, cx, cy) < max(b.bw, b.bh) * 0.8 + 1.4:
            u.path = None
            u.anim = "gather"
            u.anim_t = 0.0
            self.face_to(u, cx, cy)
            b.builders = 1
            b.hp = min(b.max_hp, max(b.hp, int(b.max_hp * max(0.1, b.build_progress))))
        else:
            if not u.path or u.path_i >= len(u.path) or u.repath_t <= 0:
                near = self.node_adjacent(u, cx, cy, b.bw, b.bh)
                if near:
                    self._set_path(u, near)
                u.repath_t = 0.8
            u.repath_t -= dt
            self.follow_path(u, dt)
            u.anim = "walk"

    def update_return(self, u, dt):
        u.order = None

    # ------------------------------------------------------------------ buildings
    def update_building(self, b, dt):
        if b.build_progress < 1:
            builders = 0
            for u in self.entities:
                if u.alive and u.worker and u.order and u.order.get("type") == "build" and u.order.get("target") is b:
                    if dist(u.x, u.y, b.x + b.bw / 2, b.y + b.bh / 2) < max(b.bw, b.bh) * 0.8 + 1.6:
                        builders += 1
            if b.team == ENEMY:
                builders = max(builders, 1)
            b.builders = builders
            if builders:
                speed = 1.0 / max(4, BUILDINGS[b.bid]["build_time"])
                b.build_progress = min(1.0, b.build_progress + dt * speed * (1 + (builders - 1) * 0.5))
                b.hp = max(b.hp, int(b.max_hp * max(0.1, b.build_progress)))
                if b.build_progress >= 1:
                    b.hp = b.max_hp
                    self.play("build_done")
                    if b.team == PLAYER:
                        self.alert(BUILDINGS[b.bid]["name"] + " completed.")
            return
        if b.queue:
            q = b.queue[0]
            q["progress"] += dt
            if q["progress"] >= q["time"]:
                b.queue.pop(0)
                self.finish_train(b, q["type"])
        if b.research:
            b.research["t"] += dt
            up = UPGRADES[b.research["id"]]
            if b.research["t"] >= up["time"]:
                self.finish_research(up)
                b.research = None
        if b.range > 0:
            if b.attack_cd > 0:
                b.attack_cd -= dt
            tgt = self.nearest_enemy(b, b.range + 0.5) if b.attack_cd <= 0 else None
            if tgt:
                b.attack_cd = b.cooldown
                self.spawn_projectile(b, tgt, "frost" if b.bid == "bonetower" else "arrow")
        if b.is_hero:
            pass

    def finish_train(self, b, utype):
        d = UNITS[utype]
        pos = None
        if b.rally:
            pos = b.rally
        else:
            pos = self.find_spawn_spot(b)
        if not pos:
            self.alert("No room to deploy units.")
            return
        u = self.spawn_unit(utype, pos[0], pos[1], b.team)
        u.order = None
        self.stats["units_trained"] += 1
        self.play("select")
        if b.rally:
            self.cmd_move([u], b.rally[0], b.rally[1])
        self.burst(pos[0], pos[1], (255, 220, 160), 5, 0.6)
        if utype == "knight" and not self.announced.get("knight"):
            self.announced["knight"] = 1
            self.alert("The Ember Knights ride.")

    def find_spawn_spot(self, b):
        for r in range(1, max(b.bw, b.bh) + 3):
            for yy in range(int(b.y) - r, int(b.y) + b.bh + r + 1):
                for xx in range(int(b.x) - r, int(b.x) + b.bw + r + 1):
                    if walkable(self.map, xx, yy, self.blocked):
                        # prefer outside footprint
                        if not (b.x <= xx < b.x + b.bw and b.y <= yy < b.y + b.bh):
                            return (xx + 0.5, yy + 0.5)
        return None

    def finish_research(self, up):
        self.upgrades.add(up["id"])
        if up["apply"] == "dmg":
            self.dmg_bonus += up["amount"]
        else:
            self.armor_bonus += up["amount"]
        self.alert(up["name"] + " researched.")
        self.play("build_done")

    # ------------------------------------------------------------------ combat
    def damage(self, tgt, amount, source, dtype="normal"):
        if not tgt or not tgt.alive:
            return
        mult = damage_mult(dtype, tgt.armor_type)
        armor = tgt.armor + (self.armor_bonus if tgt.team == PLAYER and not tgt.is_building else 0)
        amount = amount * mult * max(0.35, 1 - armor * 0.055)
        if tgt.shield_hp > 0:
            absorb = min(tgt.shield_hp, amount)
            tgt.shield_hp -= absorb
            amount -= absorb
            self.burst(tgt.x, tgt.y, (255, 200, 120), 4, 0.5)
        if amount <= 0:
            return
        tgt.hp -= amount
        st = getattr(source, "team", None)
        if isinstance(source, dict):
            st = source.get("team")
        self.stats["damage"] += amount if st == PLAYER else 0
        if tgt.hp <= 0:
            self.kill(tgt, source)

    def hit_fx(self, tgt):
        self.burst(tgt.x, tgt.y, (180, 40, 40), 5, 0.5)
        if self.rng.random() < 0.5:
            self.play("sword")

    def kill(self, tgt, source):
        if not tgt or not tgt.alive:
            return
        src_team = getattr(source, "team", None)
        if isinstance(source, dict):
            src_team = source.get("team")
        tgt.alive = False
        tgt.hp = 0
        tgt.death_t = 0
        tgt.anim = "death"
        tgt.anim_t = 0
        tgt.order = None
        tgt.target = None
        if tgt.is_building:
            for t in tgt.blocked_tiles:
                self.blocked.discard(t)
            self.burst(tgt.x + tgt.bw / 2, tgt.y + tgt.bh / 2, (80, 70, 60), 30, 1.8)
            self.play("explosion")
            if self.game:
                self.game.shake(9, 0.5)
            if tgt.bid == "necropolis":
                self.end_mission("victory")
        else:
            if src_team == PLAYER:
                self.stats["kills"] += 1
                self.gold += int(tgt.bounty * 0.5)
                if self.hero and self.hero.alive and dist(self.hero.x, self.hero.y, tgt.x, tgt.y) < 16:
                    self.gain_xp(self.hero, tgt.xp_value)
            elif src_team == ENEMY:
                if tgt.team == PLAYER:
                    self.stats["losses"] += 1
            self.burst(tgt.x, tgt.y, (150, 40, 40), 10, 0.9)
            self.play("death")
            if tgt.is_hero and tgt.team == PLAYER:
                tgt.hero_revive_t = 45.0
                self.alert("Marshal Aldric has fallen. He will return at the Altar.")
                self.play("alert")
        if tgt.team == NEUTRAL:
            self.check_camp(tgt)

    def check_camp(self, u):
        name = getattr(u, "camp", None)
        if not name or name in self.camp_cleared:
            return
        alive = [e for e in self.entities if e.alive and e.team == NEUTRAL and getattr(e, "camp", "") == name]
        if not alive:
            self.camp_cleared.add(name)
            self.gold += 120
            self.alert(f"{name} cleared. +120 gold")
            self.play("gold")

    def gain_xp(self, hero, amount):
        if not hero or not hero.alive:
            return
        hero.xp += amount
        lv = 1
        for i, th in enumerate(HERO_LEVELS):
            if hero.xp >= th:
                lv = i + 1
        if lv > hero.level:
            while hero.level < lv:
                hero.level += 1
                hero.max_hp += HERO_GROWTH["hp"]
                hero.hp = min(hero.max_hp, hero.hp + HERO_GROWTH["hp"])
                hero.max_mana += HERO_GROWTH["mana"]
                hero.mana = min(hero.max_mana, hero.mana + HERO_GROWTH["mana"])
                hero.dmg_min += HERO_GROWTH["dmg"]
                hero.dmg_max += HERO_GROWTH["dmg"]
            self.burst(hero.x, hero.y, (255, 210, 120), 22, 1.4)
            self.alert(f"Aldric reaches level {hero.level}.")
            self.play("level")

    def spawn_projectile(self, src, tgt, ptype):
        p = dict(x=src.x, y=src.y, z=src.height + 0.55, sx=src.x, sy=src.y,
                 tgt=tgt, speed=PROJECTILES.get(ptype, PROJECTILES["arrow"])["speed"],
                 type=ptype, dmg=self.rng.uniform(src.dmg_min, src.dmg_max),
                 dtype=src.damage_type, team=src.team, t=0.0, dur=0.0)
        d = dist(src.x, src.y, tgt.x + (tgt.bw / 2 if tgt.is_building else 0),
                 tgt.y + (tgt.bh / 2 if tgt.is_building else 0))
        p["dur"] = max(0.15, d / p["speed"])
        self.projectiles.append(p)

    def update_projectiles(self, dt):
        for p in list(self.projectiles):
            p["t"] += dt
            f = clamp(p["t"] / p["dur"], 0, 1)
            tgt = p["tgt"]
            if not tgt or not tgt.alive:
                self.projectiles.remove(p)
                continue
            tx = tgt.x + (tgt.bw / 2 if tgt.is_building else 0)
            ty = tgt.y + (tgt.bh / 2 if tgt.is_building else 0)
            p["x"] = p["sx"] + (tx - p["sx"]) * f
            p["y"] = p["sy"] + (ty - p["sy"]) * f
            p["z"] = p["start_z"] if "start_z" in p else p["z"]
            if f >= 1:
                self.damage(tgt, p["dmg"], p, p["dtype"])
                self.hit_fx(tgt)
                self.projectiles.remove(p)

    # ------------------------------------------------------------------ fx
    def burst(self, x, y, color, n=8, power=1.0):
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            sp = self.rng.uniform(0.2, 1.3) * power
            self.particles.append(dict(x=x, y=y + 0.2, z=self.map.height_at(int(x), int(y)) + 0.4,
                                       vx=math.cos(a) * sp, vy=math.sin(a) * sp * 0.6,
                                       vz=self.rng.uniform(0.4, 1.6) * power,
                                       life=self.rng.uniform(0.3, 0.8) * power,
                                       max_life=0.8 * power,
                                       color=color, r=self.rng.uniform(1.2, 3.0) * power, glow=True))

    def update_particles(self, dt):
        for p in list(self.particles):
            p["life"] -= dt
            if p["life"] <= 0:
                self.particles.remove(p)
                continue
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["z"] += p["vz"] * dt
            p["vz"] -= 2.0 * dt
            if p["z"] < 0.2:
                p["z"] = 0.2
                p["vz"] = 0

    # ------------------------------------------------------------------ alerts/mission
    def alert(self, text):
        self._alerts.append({"text": text, "t": 4.0})
        if len(self._alerts) > 4:
            self._alerts.pop(0)

    def _alert_tick(self, dt):
        for a in list(self._alerts):
            a["t"] -= dt
            if a["t"] <= 0:
                self._alerts.remove(a)

    def play(self, name):
        if self.sfx:
            self.sfx.play(name)

    def update_mission(self, dt):
        if not self.started or self.state != "playing":
            return
        t = self.time
        if t > 90 and "stir" not in self.announced:
            self.announced["stir"] = 1
            self.alert("The Hollow Host stirs beyond the ford.")
            self.play("horn")
        if self.ai:
            self.ai.mission_update(dt)
        # hero revive
        h = self.hero
        if h and not h.alive and h.hero_revive_t > 0 and self.state == "playing":
            h.hero_revive_t -= dt
            if h.hero_revive_t <= 0:
                altars = [b for b in self.buildings_of(PLAYER) if b.bid == "altar" and b.build_progress >= 1]
                spot = None
                if altars:
                    spot = self.find_spawn_spot(altars[0])
                if spot:
                    self.hero = self.spawn_unit("hero", spot[0], spot[1], PLAYER)
                    self.hero.level = h.level
                    self.hero.xp = h.xp
                    self.hero.alert_ready = True
                    self.alert("Marshal Aldric returns to the fight.")
                    self.play("level")
        player_b = self.buildings_of(PLAYER)
        player_u = self.units_of(PLAYER)
        if not player_b and not player_u and self.state == "playing":
            self.end_mission("defeat")

    def end_mission(self, result):
        if self.state != "playing":
            return
        self.state = result
        self.mode = result
        self.end_t = self.time
        self.play("victory" if result == "victory" else "defeat")
        if self.game:
            self.game.on_mission_end(result)
