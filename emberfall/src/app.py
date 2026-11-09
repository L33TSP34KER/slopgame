"""Emberfall application: window, state machine, input, camera, QA hooks."""
from __future__ import annotations
import argparse, json, math, os, sys, time
import pygame
from .defs import *
from .mapgen import generate_map
from .art import Art
from .render import Renderer, Camera
from .world import World
from .ai import EnemyAI
from .audio import Audio
from .ui import UI
from .core import clamp, dist


def _desktop_size():
    try:
        sizes = pygame.display.get_desktop_sizes()
        if sizes:
            return sizes[0]
    except Exception:
        pass
    return (1600, 900)


def default_window_size():
    """Largest sane 16:9 window that fits the desktop without going under 960x540."""
    if os.environ.get("SDL_VIDEODRIVER") == "dummy":
        return (SCREEN_W, SCREEN_H)
    sw, sh = _desktop_size()
    for w, h in ((1600, 900), (1280, 720), (1152, 648), (960, 540)):
        if w <= sw - 40 and h <= sh - 80:
            return (w, h)
    return (min(SCREEN_W, max(960, sw)), min(SCREEN_H, max(540, sh)))


def open_display(fullscreen: bool):
    """Compatibility wrapper for older QA probes."""
    return open_window(fullscreen)


def open_window(fullscreen, size=None):
    """Borderless OS window; the game renders to a fixed 1600x900 canvas.

    A normal decorated window is force-tiled by the user's Wayland compositor
    (observed 1600x900 -> 950x1020). NOFRAME is treated as a floating game
    surface and keeps the requested 16:9 size. Fullscreen uses the desktop
    size with the same borderless path, then letterboxes the canvas.
    """
    if fullscreen:
        sw, sh = _desktop_size()
        try:
            return pygame.display.set_mode((sw, sh), pygame.NOFRAME)
        except pygame.error:
            pass
    w, h = size or default_window_size()
    try:
        return pygame.display.set_mode((w, h), pygame.NOFRAME)
    except pygame.error:
        return pygame.display.set_mode((w, h))

class Game:
    def __init__(self, args=None):
        self.args = args or argparse.Namespace(difficulty="knight", qa=False, shot=None,
                                               frames=0, scene="base", speed=1.0,
                                               fullscreen=False, music=0.5, sfx=0.72, autoplay=False)
        pygame.mixer.pre_init(44100, -16, 2, 512)
        os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
        os.environ.setdefault("SDL_VIDEO_X11_WMCLASS", "Emberfall")
        os.environ.setdefault("SDL_APP_ID", "Emberfall")
        pygame.init()
        self.fullscreen = bool(getattr(self.args, "fullscreen", False))
        self.window = open_window(self.fullscreen)
        # ALL game rendering goes to this logical canvas; present() letterboxes it.
        self.screen = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
        pygame.display.set_caption("Emberfall — The Hollow Crown")
        self.clock = pygame.time.Clock()
        self.art = Art()
        self.map = generate_map()
        self.audio = Audio()
        self.sfx = self.audio
        self.difficulty = self.args.difficulty
        self.world = World(self, self.map, self.art, self.difficulty)
        self.world.mode = "menu"
        self.world.started = False
        self.world.ai = EnemyAI(self.world)
        self.renderer = Renderer(self.world)
        self.camera = Camera(*self.renderer.w2s(24, 69, 1), self.renderer.cam_bounds())
        self.camera.clamp()
        self.ui = UI(self)
        self.state = "title"
        self.state_before = "title"
        self.selection = []
        self.control_groups = {}
        self.build_menu = False
        self.placement = None
        self.attack_move_mode = False
        self.targeting = None
        self.rally_mode = False
        self.drag_start = None
        self.drag_now = None
        self.mouse_down_pos = None
        self.mouse = (SCREEN_W // 2, SCREEN_H // 2)
        self.mouse_tile = (24, 70)
        self.drag_cam = None
        self.menu_t = 0.0
        self.time_scale = max(0.25, float(self.args.speed or 1.0))
        self.sim_acc = 0.0
        self.sim_step = 1 / 30
        self.running = True
        self.fps = 60.0
        self.frame = 0
        self.last_state_print = 0.0
        self.stats_saved = False
        self.autoplay = bool(self.args.autoplay or os.environ.get("EMBERFALL_AUTOPLAY") == "1")
        self.auto_done = set()
        self.auto_train_t = 0
        self.auto_next = 0
        self.audio.set_music(self.args.music)
        self.audio.set_sfx(self.args.sfx)
        self.audio.play_music("menu")
        for i in range(len(self.world.vis)):
            self.world.explored[i] = 1
        self.qa = bool(self.args.qa or os.environ.get("EMBERFALL_QA") not in (None, "", "0"))
        if self.qa:
            self.setup_qa()

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.window = open_window(self.fullscreen)

    # ---------------------------------------------------------------- state
    def setup_qa(self):
        env = os.environ.get("EMBERFALL_QA", "")
        scene = self.args.scene or "base"
        if scene == "title":
            self.state = "title"
            return
        self.start_mission(skip_intro=True)
        if scene == "intro":
            self.state = "intro"
            self.world.started = False
            self.world.mode = "intro"
        if scene in ("base", "battle", "qa", "play"):
            self.world.gold = 4200
            self.world.lumber = 1800
            self.world.food_extra = 18
            hall = next((b for b in self.world.buildings_of(PLAYER) if b.bid == "townhall"), None)
            if hall:
                for bid, ox, oy in (("barracks", 24, 64), ("farm", 14, 70), ("blacksmith", 18, 74),
                                    ("tower", 12, 66), ("sanctum", 22, 76), ("farm", 26, 76),
                                    ("farm", 10, 74), ("farm", 16, 78)):
                    if self.world.can_place(bid, ox, oy):
                        self.world.spawn_building(bid, ox, oy, PLAYER, complete=True)
            for i, rig in enumerate(("footman", "footman", "archer", "archer", "knight",
                                     "priest", "footman", "archer", "knight")):
                ang = i / 9 * 6.283
                u = self.world.spawn_unit(rig, 23.0 + math.cos(ang) * 3.6,
                                          70.0 + math.sin(ang) * 2.6, PLAYER)
                u.order = None
            self.world.hero.x, self.world.hero.y = 24, 72
            self.world.update_fog(force=True)
            for i in range(len(self.world.vis)):
                self.world.explored[i] = 1
            self.center_camera(22, 69)
            self.select([self.world.hero])
        if scene == "battle":
            enemy = self.world.spawn_unit("ghoul", 29, 71, ENEMY)
            enemy2 = self.world.spawn_unit("fiend", 31, 70, ENEMY)
            enemy3 = self.world.spawn_unit("abomination", 30, 73, ENEMY)
            self.world.cmd_attack_move([u for u in self.world.units_of(PLAYER) if not u.worker], 30, 72)
            self.center_camera(27, 71)
        if scene == "siege":
            self.world.gold = 9000
            self.world.lumber = 4000
            for i in range(22):
                u = self.world.spawn_unit("knight" if i % 3 == 0 else "archer" if i % 2 else "footman",
                                          58 + (i % 5) * 0.9, 27 + (i // 5) * 0.9, PLAYER)
                u.order = None
            self.world.cmd_attack_move([u for u in self.world.units_of(PLAYER) if not u.worker], 61, 20)
            self.world.update_fog(force=True)
            for i in range(len(self.world.vis)):
                self.world.explored[i] = 1
            self.center_camera(60, 24)
        if scene == "defeat":
            for b in list(self.world.buildings_of(PLAYER)):
                self.world.damage(b, 99999, None, "normal")
            for u in list(self.world.units_of(PLAYER)):
                self.world.damage(u, 99999, None, "normal")
        if scene == "victory":
            self.world.stats.update(kills=48, losses=11, gold_gathered=5200, lumber_gathered=2400)
            self.world.hero.level = 6
            self.world.state = "victory"
            self.state = "victory"
        if scene == "defeat":
            self.world.state = "defeat"
            self.state = "defeat"

    def start_mission(self, difficulty=None, skip_intro=False):
        diff = difficulty or self.difficulty
        self.difficulty = diff
        self.world = World(self, self.map, self.art, diff)
        self.world.ai = EnemyAI(self.world)
        self.world.mode = "play" if skip_intro else "intro"
        self.world.started = skip_intro
        self.renderer.game = self.world
        self.selection = []
        self.build_menu = False
        self.placement = None
        self.attack_move_mode = False
        self.targeting = None
        self.world.placement = None
        # The vale is charted from the start; live units still obey visibility (vis),
        # so the opening frame is a readable battlefield instead of a black wedge.
        self.world.explored[:] = b"\x01" * len(self.world.explored)
        # Initial fog pocket: enough vale to read the opening, not the enemy base.
        hall = next((b for b in self.world.buildings_of(PLAYER) if b.bid in ("townhall", "keep")), None)
        rx, ry = ((hall.x + hall.bw / 2, hall.y + hall.bh / 2) if hall else (24.5, 71.5))
        for yy in range(int(ry) - 19, int(ry) + 20):
            for xx in range(int(rx) - 19, int(rx) + 20):
                if 0 <= xx < self.world.map.w and 0 <= yy < self.world.map.h:
                    if (xx - rx) ** 2 + (yy - ry) ** 2 <= 19 * 19:
                        self.world.explored[yy * self.world.map.w + xx] = 1
        if self.world.hero and self.world.hero.alive:
            self.select([self.world.hero])
        cx, cy = self.renderer.w2s(24, 68, 1) if skip_intro else self.renderer.w2s(33, 60, 1)
        self.camera = Camera(cx, cy, self.renderer.cam_bounds())
        self.camera.clamp()
        self.state = "play" if skip_intro else "intro"
        self.state_before = "play"
        self.menu_t = 0.0
        self.world.started = skip_intro
        if skip_intro:
            self.audio.play_music("battle")
        else:
            self.audio.play_music("menu")

    def begin_mission(self):
        self.world.started = True
        self.world.mode = "play"
        self.world.update_fog(force=True)
        self.state = "play"
        self.audio.play_music("battle")
        self.world.alert("The vale is yours to hold, Marshal. Raise the Emberhold.")
        self.world.play("command")

    def on_mission_end(self, result):
        self.state = result
        self.stats_saved = True
        try:
            best = int(open(os.path.join(os.path.dirname(__file__), "..", "..", "design", ".best")).read())
        except Exception:
            best = 0
        # leave file handling to UI / release notes

    def shake(self, power=6, duration=0.3):
        self.camera.shake(power, duration)

    # ---------------------------------------------------------------- selection
    def selected(self):
        return [e for e in self.selection if e.alive]

    def select(self, ents, add=False):
        if not add:
            for e in self.selection:
                e.selected = False
            self.selection = []
        for e in ents:
            if e and e.alive and e not in self.selection:
                e.selected = True
                self.selection.append(e)

    def clear_selection(self):
        self.select([])

    def center_camera(self, tx, ty):
        px, py = self.renderer.w2s(tx, ty, 1)
        self.camera.x, self.camera.y = px, py
        self.camera.clamp()

    def idle_worker(self):
        for u in self.world.units_of(PLAYER):
            if u.worker and (u.order is None or u.order.get("type") not in ("gather", "build")):
                self.select([u])
                self.center_camera(u.x, u.y)
                return

    # ---------------------------------------------------------------- picking / orders
    def screen_pos(self, e):
        px, py = self.renderer.w2s(e.x + (e.bw / 2 if e.is_building else 0),
                                   e.y + (e.bh / 2 if e.is_building else 0), e.height)
        return (px - self.camera.x + SCREEN_W / 2, py - self.camera.y + SCREEN_H / 2)

    def pick_entity(self, mx, my):
        best = None
        bd = 1e9
        for e in self.world.entities:
            if not e.alive:
                continue
            if e.team != PLAYER:
                tx, ty = int(e.x), int(e.y)
                if 0 <= tx < self.map.w and 0 <= ty < self.map.h:
                    if not self.world.vis[ty * self.map.w + tx]:
                        continue
            px, py = self.screen_pos(e)
            if e.is_building:
                r = max(e.bw, e.bh) * 34
                d = abs(mx - px) + abs(my - py) * 1.6
                if d < r and d < bd:
                    best, bd = e, d
            else:
                d = math.hypot(mx - px, my - (py - 18))
                if d < 26 and d < bd:
                    best, bd = e, d
        return best

    def box_select(self, x0, y0, x1, y1, add=False):
        r = pygame.Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
        picked = []
        for e in self.world.units_of(PLAYER):
            px, py = self.screen_pos(e)
            if r.collidepoint(px, py - 10):
                picked.append(e)
        self.select(picked, add=add)
        return len(picked)

    def resource_at(self, tx, ty):
        if (tx, ty) in self.map.wood:
            return {"type": "wood", "x": tx, "y": ty}
        for mine in self.map.mines:
            if mine["gold"] > 0 and mine["x"] - 1 <= tx <= mine["x"] and mine["y"] - 1 <= ty <= mine["y"]:
                return {"type": "gold", "mine": mine}
        return None

    def context_order(self, mx, my):
        sel = self.selected()
        if not sel:
            return
        tile = self.renderer.screen_to_tile(mx, my, self.camera)
        tx, ty = tile
        target = self.pick_entity(mx, my)
        tgt_team = target.team if target else None
        if target and tgt_team == PLAYER and target.is_building and target.build_progress < 1:
            workers = [u for u in sel if u.worker]
            if workers:
                for u in workers:
                    self.world.order_build(u, target)
                return
        if target and tgt_team == PLAYER and target.is_building:
            if all(u.is_building for u in sel):
                self.world.cmd_rally(target if target.is_building else sel[0], tile[0] + 0.5, tile[1] + 0.5)
                return
        res = self.resource_at(tx, ty)
        if res:
            workers = [u for u in sel if u.worker]
            if workers:
                self.world.cmd_gather(workers, res)
                return
        if target and tgt_team in (ENEMY, NEUTRAL) and not self.is_friendly_neutral(target):
            self.world.cmd_attack([u for u in sel if not u.is_building], target)
            return
        if all(u.is_building for u in sel):
            self.world.cmd_rally(sel[0], tile[0] + 0.5, tile[1] + 0.5)
            return
        units = [u for u in sel if not u.is_building]
        if units:
            self.world.cmd_move(units, tile[0] + 0.5, tile[1] + 0.5)

    def is_friendly_neutral(self, e):
        return False

    def place_building(self, mx, my):
        if not self.placement:
            return
        tile = self.renderer.screen_to_tile(mx, my, self.camera)
        bid = self.placement["bid"]
        workers = [u for u in self.selected() if u.worker]
        b = self.world.cmd_build(workers, bid, tile[0], tile[1])
        if b:
            self.placement = None
            self.world.placement = None
            self.ui.build_menu = False
            self.build_menu = False

    def cast_at(self, mx, my):
        if not self.targeting:
            return
        aid = self.targeting["aid"]
        hero = self.world.hero
        tile = self.renderer.screen_to_tile(mx, my, self.camera)
        target = self.pick_entity(mx, my)
        if ABILITIES[aid]["target"] == "unit":
            self.world.cmd_cast(hero, aid, target if target and target.team != PLAYER else None)
        else:
            self.world.cmd_cast(hero, aid, target if target else (tile[0] + 0.5, tile[1] + 0.5))
        self.targeting = None
        self.world.targeting = None

    # ---------------------------------------------------------------- actions
    def handle_action(self, a):
        k = a.get("kind")
        if k in ("noop", None):
            return
        w = self.world
        if k == "menu":
            act = a.get("action")
            if act == "campaign":
                self.start_mission("knight", skip_intro=False)
            elif act == "skirmish":
                self.state = "skirmish"
                self.state_before = "title"
            elif act == "difficulty":
                self.start_mission(a.get("value", "knight"), skip_intro=False)
            elif act == "begin":
                self.begin_mission()
            elif act == "resume":
                self.state = "play"
                w.paused = False
            elif act == "pause":
                self.state = "paused"
                w.paused = True
            elif act == "restart":
                self.start_mission(self.difficulty, skip_intro=True)
            elif act == "title":
                self.to_title()
            elif act == "settings":
                self.state_before = self.state
                self.state = "settings"
            elif act == "controls":
                self.state_before = self.state
                self.state = "controls"
            elif act == "credits":
                self.state_before = self.state
                self.state = "credits"
            elif act == "back":
                self.state = self.state_before
            elif act == "objectives":
                self.ui.show_objectives = not self.ui.show_objectives
            elif act == "vol":
                f = a.get("field"); d = a.get("delta", 0)
                if f == "music":
                    self.audio.set_music(self.audio.music_vol + d)
                elif f == "sfx":
                    self.audio.set_sfx(self.audio.sfx_vol + d)
            elif act == "buildmenu":
                self.ui.build_menu = True
            elif act == "buildback":
                self.ui.build_menu = False
            elif act == "subgroup":
                groups = self.ui.subgroups()
                i = a.get("index", 0)
                if 0 <= i < len(groups):
                    self.select(groups[i])
            elif act == "quit":
                self.running = False
            return
        if k == "buildmenu":
            self.ui.build_menu = True
            self.build_menu = True
            return
        if k == "buildback":
            self.ui.build_menu = False
            self.build_menu = False
            return
        if k == "train":
            w.cmd_train(a["building"], a["unit"])
        elif k == "research":
            w.cmd_research(a["building"], a["upgrade"])
        elif k == "queue_cancel":
            w.cmd_cancel_queue(a["building"])
        elif k == "build":
            self.placement = {"bid": a["bid"]}
            w.placement = self.placement
            self.build_menu = False
            self.ui.build_menu = False
        elif k == "upgrade_keep":
            b = a.get("building")
            if b:
                w.cmd_research(b, "keep") if False else None
        elif k == "ability":
            aid = a["ability"]
            hero = w.hero
            ab = ABILITIES[aid]
            if ab["target"] == "self":
                w.cmd_cast(hero, aid)
            elif ab["target"] == "unit":
                self.targeting = {"aid": aid}
                w.targeting = self.targeting
            else:
                self.targeting = {"aid": aid}
                w.targeting = self.targeting
        elif k == "stop":
            w.cmd_stop([u for u in self.selected() if not u.is_building])
        elif k == "hold":
            w.cmd_hold([u for u in self.selected() if not u.is_building])
        elif k == "attackmove":
            self.attack_move_mode = True
            w.attack_move_mode = True
        elif k == "gather":
            for u in self.selected():
                if u.worker:
                    node = w.nearest_node(u)
                    if node:
                        w.cmd_gather([u], node)
        elif k == "rally":
            self.rally_mode = True
            w.alert("Choose a rally point.")
            return
        elif k == "minimap":
            tx, ty = a["x"], a["y"]
            if a.get("button", 1) == 3:
                units = [u for u in self.selected() if not u.is_building]
                if units:
                    w.cmd_move(units, tx, ty)
            else:
                self.center_camera(tx, ty)

    # ---------------------------------------------------------------- events
    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.running = False
            return
        if ev.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWSIZECHANGED", -1)):
            return
        if ev.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            # window pixel -> logical 1600x900 (the picture is scaled/letterboxed)
            mapped = self.map_pos(ev.pos, clamp_out=(ev.type != pygame.MOUSEBUTTONDOWN))
            if mapped is None:            # click landed in the letterbox: ignore
                return
            if tuple(mapped) != tuple(ev.pos):
                ev = pygame.event.Event(ev.type, dict(ev.dict, pos=mapped))
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 2:
            self.drag_cam = (ev.pos, self.camera.x, self.camera.y)
            return
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 2:
            self.drag_cam = None
            return
        if ev.type == pygame.KEYDOWN:
            self.handle_key(ev)
            return
        if ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = ev.pos
            if ev.button == 3:
                if self.placement:
                    self.placement = None; self.world.placement = None; return
                if self.targeting:
                    self.targeting = None; self.world.targeting = None; return
                if self.attack_move_mode:
                    self.attack_move_mode = False; self.world.attack_move_mode = False; return
            act = self.ui.take_action((mx, my), ev.button)
            if act:
                act["button"] = ev.button
                self.handle_action(act)
                return
            if self.state in ("title", "skirmish", "intro", "paused", "victory", "defeat", "settings", "controls", "credits"):
                return
            if self.state == "play":
                if ev.button == 1:
                    if self.placement:
                        self.place_building(mx, my); return
                    if self.targeting:
                        self.cast_at(mx, my); return
                    if self.rally_mode:
                        tile = self.renderer.screen_to_tile(mx, my, self.camera)
                        for b in self.selected():
                            if b.is_building:
                                self.world.cmd_rally(b, tile[0] + 0.5, tile[1] + 0.5)
                        self.rally_mode = False
                        return
                    if self.attack_move_mode:
                        tile = self.renderer.screen_to_tile(mx, my, self.camera)
                        units = [u for u in self.selected() if not u.is_building]
                        if units:
                            self.world.cmd_attack_move(units, tile[0] + 0.5, tile[1] + 0.5)
                        self.attack_move_mode = False; self.world.attack_move_mode = False
                        return
                    self.mouse_down_pos = (mx, my)
                    self.drag_start = (mx, my)
                    self.drag_now = (mx, my)
                    self.world.drag_start = self.drag_start
                    self.world.drag_now = self.drag_now
                elif ev.button == 3:
                    self.context_order(mx, my)
            return
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            if self.state == "play" and self.drag_start:
                x0, y0 = self.drag_start
                x1, y1 = self.drag_now or (x0, y0)
                if abs(x1 - x0) + abs(y1 - y0) > 10:
                    self.box_select(x0, y0, x1, y1, add=pygame.key.get_mods() & pygame.KMOD_SHIFT)
                else:
                    self.click_select(x1, y1, add=pygame.key.get_mods() & pygame.KMOD_SHIFT)
            self.drag_start = self.drag_now = None
            self.world.drag_start = self.world.drag_now = None
            self.mouse_down_pos = None
            self.ui.release()
            return
        if ev.type == pygame.MOUSEMOTION:
            if self.drag_cam:
                (sx, sy), cx, cy = self.drag_cam
                self.camera.x = cx - (ev.pos[0] - sx)
                self.camera.y = cy - (ev.pos[1] - sy)
                self.camera.clamp()
            if self.drag_start:
                self.drag_now = ev.pos
                self.world.drag_now = ev.pos
            if self.state == "play":
                self.world.mouse_tile = self.renderer.screen_to_tile(ev.pos[0], ev.pos[1], self.camera)
            return
        if ev.type == pygame.MOUSEWHEEL:
            pass

    def click_select(self, mx, my, add=False):
        e = self.pick_entity(mx, my)
        if e:
            if e.team != PLAYER:
                self.select([e], add=add)
            else:
                # double click same type
                if not add and len(self.selection) == 1 and self.selection[0].kind == e.kind:
                    group = [u for u in self.world.units_of(PLAYER) if u.kind == e.kind
                             and self.ui.on_screen(u)]
                    self.select(group or [e], add=False)
                else:
                    self.select([e], add=add)
        else:
            if not add:
                self.clear_selection()

    def handle_key(self, ev):
        k = ev.key
        mods = pygame.key.get_mods()
        if k == pygame.K_ESCAPE:
            if self.placement:
                self.placement = None; self.world.placement = None; return
            if self.targeting:
                self.targeting = None; self.world.targeting = None; return
            if self.attack_move_mode:
                self.attack_move_mode = False; self.world.attack_move_mode = False; return
            if self.ui.build_menu:
                self.ui.build_menu = False; self.build_menu = False; return
            if self.state == "play":
                self.state = "paused"; self.world.paused = True
            elif self.state in ("paused", "settings", "controls", "credits"):
                self.state = "play" if self.state != "paused" else "play"
                self.world.paused = False
            elif self.state == "skirmish":
                self.state = "title"
            return
        if self.state != "play":
            return
        if k in (pygame.K_SPACE,):
            hero = self.world.hero
            if hero and hero.alive:
                self.select([hero]); self.center_camera(hero.x, hero.y)
            return
        if k == pygame.K_F1:
            self.idle_worker(); return
        if k == pygame.K_TAB:
            self.ui.cycle_subgroup(); return
        if k == pygame.K_o:
            self.ui.show_objectives = not self.ui.show_objectives; return
        if k == pygame.K_F11 or (k in (pygame.K_RETURN, pygame.K_KP_ENTER) and (mods & pygame.KMOD_ALT)):
            self.toggle_fullscreen()
            return
        if pygame.K_1 <= k <= pygame.K_9:
            num = k - pygame.K_0
            if mods & pygame.KMOD_CTRL:
                self.control_groups[num] = list(self.selection)
            else:
                grp = self.control_groups.get(num)
                if grp:
                    self.select([e for e in grp if e.alive])
            return
        # command hotkeys from UI
        act = self.ui.hotkey_action(ev.unicode.upper() if ev.unicode else "")
        if act:
            self.handle_action(act)
            return
        if k == pygame.K_b:
            if any(u.worker for u in self.selected()):
                self.ui.build_menu = not self.ui.build_menu
                self.build_menu = self.ui.build_menu
            return
        if k == pygame.K_a:
            self.handle_action({"kind": "attackmove"}); return
        if k == pygame.K_s:
            self.handle_action({"kind": "stop"}); return
        if k == pygame.K_h:
            self.handle_action({"kind": "hold"}); return
        if k == pygame.K_g:
            self.handle_action({"kind": "gather"}); return

    # ---------------------------------------------------------------- update/draw
    def to_title(self):
        self.state = "title"
        self.selection = []
        self.build_menu = False
        self.placement = None
        self.world.placement = None
        self.targeting = None
        self.attack_move_mode = False
        self.audio.play_music("menu")

    def update(self, dt):
        if self.state == "title":
            self.menu_t += dt
            ang = self.menu_t * 0.05
            tx = 32 + math.sin(ang) * 8
            ty = 61 + math.cos(ang) * 5
            px, py = self.renderer.w2s(tx, ty, 1)
            self.camera.x += (px - self.camera.x) * min(1, dt * 0.55)
            self.camera.y += (py - self.camera.y) * min(1, dt * 0.55)
            self.camera.clamp()
        elif self.state == "play":
            keys = pygame.key.get_pressed()
            sp = 760 * dt
            # arrows only: WASD is reserved for commands (A attack-move, S stop)
            if keys[pygame.K_UP]: self.camera.y -= sp
            if keys[pygame.K_DOWN]: self.camera.y += sp
            if keys[pygame.K_LEFT]: self.camera.x -= sp
            if keys[pygame.K_RIGHT]: self.camera.x += sp
            self.camera.clamp()
            mx, my = self.map_pos(pygame.mouse.get_pos()) or (SCREEN_W // 2, SCREEN_H // 2)
            if (not self.qa and pygame.mouse.get_focused()
                    and 0 <= mx < SCREEN_W and 44 <= my < 700):
                edge = 620 * dt
                if mx <= 8: self.camera.x -= edge
                elif mx >= SCREEN_W - 9: self.camera.x += edge
                if my <= 52: self.camera.y -= edge
                self.camera.clamp()
            self.sim_acc += dt * self.time_scale
            steps = 0
            while self.sim_acc >= self.sim_step and steps < 4:
                self.world.update(self.sim_step)
                self.sim_acc -= self.sim_step
                steps += 1
            if self.sim_acc > self.sim_step * 4:
                self.sim_acc = 0
            self.world.fps = self.fps
            if self.autoplay and self.world.started:
                self.autoplay_tick()
        self.camera.update(dt)
        self.ui.update(dt)

    def _free_spot(self, bid, cx, cy, radius=9):
        for r in range(2, radius):
            for yy in range(cy - r, cy + r + 1):
                for xx in range(cx - r, cx + r + 1):
                    if self.world.can_place(bid, xx, yy):
                        return (xx, yy)
        return None

    def autoplay_tick(self):
        w = self.world
        t = w.time
        workers = [u for u in w.units_of(PLAYER) if u.worker]
        if "gather" not in self.auto_done and t > 0.6 and workers:
            mine = next((m for m in w.map.mines if not m["neutral"] and m["gold"] > 0), None)
            if mine:
                w.cmd_gather(workers, {"type": "gold", "mine": mine})
                self.auto_done.add("gather")
        # wood: keep one worker on the nearest tree, re-tasked when the node
        # runs dry. Gold-only autoplay meant every demo run ended with
        # "Lumber gathered 0" and no lumber-fed units (archers, towers),
        # which is half of why the demo lost by minute six.
        if workers and t > 1.2:
            wu = workers[-1]
            node = wu.node
            idle_for_wood = (node is None) or (node.get("type") != "wood")                 or w.node_depleted(node)
            cooldown = getattr(self, "auto_wood_t", 0.0)
            if wu.alive and idle_for_wood and t > cooldown:
                near = w.nearest_node(wu, kind="wood")
                if near:
                    w.cmd_gather([wu], {"type": "wood", "x": near["x"], "y": near["y"]})
                    self.auto_wood_t = t + 4.0
        if "farm" not in self.auto_done and t > 2.5 and workers:
            sp = self._free_spot("farm", 20, 72)
            if sp:
                w.cmd_build([workers[0]], "farm", sp[0], sp[1])
                self.auto_done.add("farm")
        if "barracks" not in self.auto_done and t > 8 and workers:
            sp = self._free_spot("barracks", 22, 62)
            if sp:
                w.cmd_build([workers[0]], "barracks", sp[0], sp[1])
                self.auto_done.add("barracks")
        if t > 18:
            hall = next((b for b in w.buildings_of(PLAYER) if b.bid in ("townhall", "keep")), None)
            if hall and t > self.auto_train_t:
                self.auto_train_t = t + 7
                w.cmd_train(hall, "worker")
            br = next((b for b in w.buildings_of(PLAYER) if b.bid == "barracks" and b.build_progress >= 1), None)
            if br and t > self.auto_train_t - 3:
                w.cmd_train(br, "archer" if int(t) % 2 else "footman")
        if t > 40 and "push" not in self.auto_done:
            army = [u for u in w.units_of(PLAYER) if not u.worker]
            if len(army) >= 6:
                w.cmd_attack_move(army, 61, 28)
                self.auto_done.add("push")
        hero = w.hero
        if hero and hero.alive:
            foes = w.nearest_enemy(hero, 6)
            if foes:
                w.cmd_cast(hero, "ember-lance", foes)

    def draw(self):
        scr = self.screen
        self.world.mouse_tile = self.mouse_tile
        self.world.mouse_pos = self.map_pos(pygame.mouse.get_pos()) or (SCREEN_W // 2, SCREEN_H // 2)
        self.renderer.draw(scr, self.world, self.camera, self.world.time if self.state != "title" else self.menu_t)
        self.ui.draw(scr)
        self.present()

    def take_shot(self, path):
        pygame.image.save(self.screen, path)

    # -------------------------------------------------- window / input mapping
    def present(self):
        """Scale the logical 1600x900 backbuffer onto the real window.

        Centre-locked and aspect-correct with letterbox bars, so the game looks
        right on any resolution (1080p, 1440p, 4K, Wayland fractional scaling,
        a resized window) instead of being stretched by the driver.
        """
        win = pygame.display.get_surface()
        if win is None:
            return
        ww, wh = win.get_size()
        scale = min(ww / SCREEN_W, wh / SCREEN_H)
        dw = max(1, int(SCREEN_W * scale))
        dh = max(1, int(SCREEN_H * scale))
        ox = (ww - dw) // 2
        oy = (wh - dh) // 2
        if dw == SCREEN_W and dh == SCREEN_H:
            win.blit(self.screen, (0, 0))
        else:
            cache = getattr(self, "_present_cache", None)
            if cache is None or cache.get_size() != (dw, dh):
                cache = pygame.Surface((dw, dh))
                self._present_cache = cache
            pygame.transform.scale(self.screen, (dw, dh), cache)
            win.fill((0, 0, 0))
            win.blit(cache, (ox, oy))
        pygame.display.flip()

    def map_pos(self, pos, clamp_out: bool = True):
        """Window pixel -> logical 1600x900 coordinate (inverse of present()).

        Returns None when the point lies in the letterbox and clamp_out is
        False (i.e. a click outside the picture is ignored instead of hitting
        whatever UI happens to live at the clamped edge).
        """
        win = pygame.display.get_surface()
        if win is None:
            return pos
        ww, wh = win.get_size()
        if ww == SCREEN_W and wh == SCREEN_H:
            return pos
        scale = min(ww / SCREEN_W, wh / SCREEN_H)
        dw, dh = SCREEN_W * scale, SCREEN_H * scale
        ox, oy = (ww - dw) / 2, (wh - dh) / 2
        x = (pos[0] - ox) / scale
        y = (pos[1] - oy) / scale
        if not (0 <= x < SCREEN_W and 0 <= y < SCREEN_H):
            if not clamp_out:
                return None
            x = min(max(x, 0), SCREEN_W - 1)
            y = min(max(y, 0), SCREEN_H - 1)
        return (int(x), int(y))
        print("SHOT", path, self.screen.get_size(), flush=True)

    def qa_state(self):
        w = self.world
        print(json.dumps(dict(
            t=round(w.time, 2), state=self.state, fps=round(self.fps, 1),
            gold=w.gold, lumber=w.lumber, food=[w.food_used(PLAYER), w.food_max(PLAYER)],
            units=len(w.units_of(PLAYER)), enemies=len(w.units_of(ENEMY)),
            sel=[e.kind for e in self.selection], camera=[round(self.camera.x), round(self.camera.y)],
            wave=getattr(getattr(w, "ai", None), "wave", 0),
            hall=max([b.hp for b in w.buildings_of(PLAYER) if b.bid in ("townhall", "keep")] or [0]),
            mode=w.state, upgrades=sorted(w.upgrades),
            music=getattr(self.audio, "_current", None), sfx_loaded=len(self.audio.sfx),
            unit_px=next(([int(v) for v in self.screen_pos(u)]
                          for u in w.units_of(PLAYER)
                          if u.alive and not u.is_building), None),
        )), flush=True)

    def run(self):
        frames = 0
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            dt = min(dt, 0.1)
            self.fps = self.clock.get_fps() or 60
            for ev in pygame.event.get():
                self.handle_event(ev)
            self.ui.poll_mouse()
            self.update(dt)
            self.draw()
            self.present()
            self.frame += 1
            frames += 1
            if self.qa and os.environ.get("EMBERFALL_QA") == "state":
                if self.world.time - self.last_state_print >= 1.0:
                    self.last_state_print = self.world.time
                    self.qa_state()
            if self.args.frames and frames >= self.args.frames:
                if self.args.shot:
                    self.take_shot(self.args.shot)
                self.running = False
            if self.args.shot and not self.args.frames and frames == 90:
                self.take_shot(self.args.shot)
                self.running = False
        pygame.quit()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Emberfall — native isometric RTS")
    p.add_argument("--difficulty", default="knight", choices=list(DIFFICULTY.keys()))
    p.add_argument("--qa", action="store_true")
    p.add_argument("--scene", default="base", choices=["title", "intro", "base", "battle", "victory", "defeat", "qa", "play", "siege"])
    p.add_argument("--shot", default=None)
    p.add_argument("--frames", type=int, default=0)
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--music", type=float, default=0.5)
    p.add_argument("--sfx", type=float, default=0.72)
    p.add_argument("--autoplay", action="store_true")
    p.add_argument("--fullscreen", action="store_true",
                   help="start in fullscreen (F11 toggles at runtime)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    g = Game(args)
    g.run()


if __name__ == "__main__":
    main()
