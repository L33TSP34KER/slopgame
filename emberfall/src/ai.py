"""Hollow Host AI: economy, production, defense, escalating waves, boss."""
from __future__ import annotations
import math, random
from .defs import *
from .core import dist, clamp

SPAWN_TABLE = [
    (0, "ghoul", 110), (140, "fiend", 150), (260, "necromancer", 180),
    (340, "abomination", 240), (430, "revenant", 210), (520, "abomination", 240),
]
BUILD_FOR = {"ghoul": "crypt", "fiend": "crypt", "necromancer": "temple",
             "abomination": "slaughterhouse", "revenant": "temple"}


class EnemyAI:
    def __init__(self, world):
        self.w = world
        self.tick = 0.0
        self.gold = 420
        self.spawn_cd = 10.0
        self.wave = 0
        self.next_wave = 240.0
        self.wave_open = False
        self.boss_awake = False
        self.rng = random.Random(4242)
        self.defenders = []

    def update(self, dt):
        w = self.w
        self.tick -= dt
        if self.tick > 0:
            return
        self.tick = 0.8
        d = w.diff
        self.gold += 7.0 * d["income"] * 0.8
        self.spawn_cd -= 0.8
        if self.spawn_cd <= 0:
            self.try_train()
        self.manage()
        self.check_boss()

    def try_train(self):
        w = self.w
        units = w.units_of(ENEMY)
        if len(units) > 58:
            self.spawn_cd = 4.0
            return
        t = w.time
        choices = [x for x in SPAWN_TABLE if x[0] <= t]
        if not choices:
            return
        _, utype, cost = choices[-1] if self.rng.random() < 0.55 else self.rng.choice(choices)
        if self.gold < cost:
            self.spawn_cd = 3.0
            return
        btype = BUILD_FOR[utype]
        b = next((x for x in w.buildings_of(ENEMY) if x.bid == btype and x.build_progress >= 1), None)
        if not b:
            self.spawn_cd = 5.0
            return
        pos = w.find_spawn_spot(b)
        if not pos:
            self.spawn_cd = 5.0
            return
        u = w.spawn_unit(utype, pos[0] + self.rng.uniform(-0.9, 0.9),
                         pos[1] + self.rng.uniform(-0.9, 0.9), ENEMY)
        u.order = {"type": "hold"}
        u.home = (b.x + b.bw / 2, b.y + b.bh / 2)
        self.gold -= cost
        self.spawn_cd = max(3.2, 8.5 * self.w.diff["wave_gap"] - w.time * 0.002)

    def manage(self):
        w = self.w
        necro = next((b for b in w.buildings_of(ENEMY) if b.bid == "necropolis"), None)
        if not necro:
            return
        # defense: player forces near the base or any building hurt
        threat = [u for u in w.units_of(PLAYER)
                  if dist(u.x, u.y, necro.x + 2.5, necro.y + 2.5) < 22]
        hurt = [b for b in w.buildings_of(ENEMY) if b.hp < b.max_hp * 0.9]
        if threat:
            idle = [u for u in w.units_of(ENEMY) if (u.order is None or u.order.get("type") == "hold")]
            for u in idle:
                if u.boss:
                    continue
                tgt = min(threat, key=lambda x: dist(u.x, u.y, x.x, x.y))
                w.cmd_attack([u], tgt)
            if threat and not getattr(self, "_def_alarm", False):
                self._def_alarm = True
                w.alert("The Host defends its crown!")
                w.play("horn")
            return
        self._def_alarm = False
        if w.time >= self.next_wave:
            self.launch_wave()

    def launch_wave(self):
        w = self.w
        self.wave += 1
        base_n = 4 + self.wave * 2
        n = int(base_n * w.diff["wave_size"])
        # free wave batch at the Necropolis so waves always feel real
        necro = next((b for b in w.buildings_of(ENEMY) if b.bid == "necropolis"), None)
        if necro:
            for i in range(n):
                pos = w.find_spawn_spot(necro)
                if not pos:
                    break
                utype = "ghoul"
                if self.wave >= 2 and i % 3 == 0:
                    utype = "fiend"
                if self.wave >= 3 and i % 5 == 0:
                    utype = "necromancer"
                if self.wave >= 4 and i % 7 == 0:
                    utype = "abomination"
                u = w.spawn_unit(utype, pos[0] + self.rng.uniform(-1.4, 1.4),
                                 pos[1] + self.rng.uniform(-1.4, 1.4), ENEMY)
                u.order = {"type": "hold"}
        # gather the standing army + the new batch
        army = [u for u in w.units_of(ENEMY) if not u.boss]
        target = self.pick_target()
        if target and army:
            for u in army:
                if u.order is None or u.order.get("type") in ("hold", "attack_move", "move"):
                    u.order = {"type": "attack_move", "x": target[0], "y": target[1]}
                    u.path = None
                    w._set_path(u, target)
        w.alert(f"Wave {self.wave}: the Hollow Host marches on the vale!")
        w.play("horn")
        if w.game:
            w.game.shake(5, 0.4)
        gap = max(85.0, 150.0 * w.diff["wave_gap"] - self.wave * 2)
        self.next_wave = w.time + gap

    def pick_target(self):
        w = self.w
        pb = w.buildings_of(PLAYER)
        if pb:
            b = min(pb, key=lambda x: (x.x - 61) ** 2 + (x.y - 18) ** 2)
            return (b.x + b.bw / 2, b.y + b.bh / 2)
        pu = w.units_of(PLAYER)
        if pu:
            return (pu[0].x, pu[0].y)
        return None

    def check_boss(self):
        w = self.w
        boss = next((u for u in w.units_of(ENEMY) if u.boss), None)
        necro = next((b for b in w.buildings_of(ENEMY) if b.bid == "necropolis"), None)
        if not boss or not necro:
            return
        if not self.boss_awake:
            near = [u for u in w.units_of(PLAYER)
                    if dist(u.x, u.y, boss.x, boss.y) < 14]
            if near or necro.hp < necro.max_hp * 0.7 or w.time > 560:
                self.boss_awake = True
                boss.order = None
                w.alert("The Hollow King rises from his throne. The vale holds its breath.")
                w.play("roar")
                if w.game:
                    w.game.shake(12, 0.7)
        if self.boss_awake and (boss.order is None or boss.order.get("type") == "hold"):
            tgt = w.nearest_enemy(boss, 22)
            if tgt:
                w.cmd_attack([boss], tgt)
            else:
                t = self.pick_target()
                if t:
                    boss.order = {"type": "attack_move", "x": t[0], "y": t[1]}
                    w._set_path(boss, t)

    def mission_update(self, dt):
        pass
