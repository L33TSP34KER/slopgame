"""Emberfall UI: HUD, command card, minimap, tooltips, title, briefing, menus."""
from __future__ import annotations
import math, os
import pygame
from .defs import *
from .core import clamp, fmt_time, fmt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INK = (22, 17, 15)
WALNUT = (38, 29, 23)
WALNUT_L = (55, 42, 32)
PARCH = (232, 220, 194)
PARCH_D = (190, 176, 148)
GOLD = (201, 162, 39)
GOLD_L = (235, 200, 110)
BRASS = (146, 112, 58)
BLOOD = (158, 52, 44)
STEEL = (182, 190, 198)
GREEN = (118, 188, 112)
BLUE = (92, 132, 210)
VIOLET = (158, 118, 208)
MUTED = (138, 126, 108)
BASE_KEYS = ["Q", "W", "E", "R", "A", "S", "D", "F", "Z", "X", "C", "V"]


class UI:
    def __init__(self, game):
        self.g = game
        self.art = game.art
        self.actions = []
        self.hover_action = None
        self.mouse = (0, 0)
        self.show_objectives = False
        self.build_menu = False
        self.shop_open = False
        self.subgroup = 0
        self.release_pos = None
        self.pulse = 0.0
        self.logo = None
        self._grad = None
        self.tooltip_cache = None
        self.minimap_rect = pygame.Rect(1372, 716, 204, 200)
        self.minimap = None
        self._mm_fog = None
        self._mm_t = -1.0
        self._mm_base = None
        self.settings_state = dict(music=game.audio.music_vol, sfx=game.audio.sfx_vol)

    # ---------------------------------------------------------------- utils
    def t(self, text, size, color=PARCH, face="serif", shadow=True):
        return self.art.text(text, size, color, face, shadow)

    def panel(self, rect, fill=WALNUT, border=BRASS, alpha=245, radius=6):
        s = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(s, (*fill, alpha), (0, 0, rect.w, rect.h), border_radius=radius)
        pygame.draw.rect(s, (*border, 255), (0, 0, rect.w, rect.h), 1, border_radius=radius)
        pygame.draw.rect(s, (0, 0, 0, 70), (2, 2, rect.w - 4, rect.h - 4), 1, border_radius=radius)
        self.g.screen.blit(s, rect.topleft)
        return s

    def line(self, x0, y0, x1, y1, col=BRASS, w=1):
        pygame.draw.line(self.g.screen, col, (x0, y0), (x1, y1), w)

    def bar(self, rect, frac, col, back=(18, 14, 13)):
        pygame.draw.rect(self.g.screen, back, rect, border_radius=3)
        pygame.draw.rect(self.g.screen, col, (rect.x, rect.y, max(1, int(rect.w * clamp(frac, 0, 1))), rect.h), border_radius=3)
        pygame.draw.rect(self.g.screen, (8, 6, 6), rect, 1, border_radius=3)

    def icon(self, key, size=32):
        return self.art.icon(key, size)

    def add(self, rect, **action):
        a = dict(action)
        a["rect"] = pygame.Rect(rect)
        self.actions.append(a)
        return a

    def button(self, rect, label, action, enabled=True, style="wood", icon=None, hotkey=None):
        r = pygame.Rect(rect)
        hover = r.collidepoint(self.mouse) and enabled
        if style == "wood":
            bg = (62, 46, 34) if hover else (45, 34, 27)
            bd = GOLD_L if hover else BRASS
        elif style == "danger":
            bg = (92, 40, 34) if hover else (66, 31, 28)
            bd = (200, 100, 84) if hover else (130, 62, 52)
        elif style == "flat":
            bg = (30, 24, 21, 0); bd = (0, 0, 0, 0)
        else:
            bg = (52, 42, 34); bd = BRASS
        if style != "flat":
            pygame.draw.rect(self.g.screen, bg, r, border_radius=5)
            pygame.draw.rect(self.g.screen, bd, r, 1, border_radius=5)
        if icon:
            im = self.icon(icon, min(r.h - 8, 34))
            self.g.screen.blit(im, (r.x + 6, r.y + (r.h - im.get_height()) // 2))
            tx = r.x + im.get_width() + 12
        else:
            tx = r.centerx
        col = PARCH if enabled else MUTED
        lab = self.t(label, 16 if r.h <= 36 else 19, col, "serif")
        if icon:
            self.g.screen.blit(lab, (tx, r.centery - lab.get_height() // 2))
        else:
            self.g.screen.blit(lab, (tx - lab.get_width() // 2, r.centery - lab.get_height() // 2))
        if hotkey:
            hk = self.t(hotkey, 12, GOLD if enabled else MUTED, "sans")
            self.g.screen.blit(hk, (r.right - hk.get_width() - 5, r.y + 3))
        if enabled:
            self.add(r, kind="menu", action=action[0] if isinstance(action, tuple) else action, **action[1] if isinstance(action, tuple) else {})
        return r

    # ---------------------------------------------------------------- lifecycle
    def update(self, dt):
        self.pulse += dt

    def poll_mouse(self):
        # window pixel -> logical 1600x900 (the game is letterboxed/scaled)
        mapped = self.g.map_pos(pygame.mouse.get_pos())
        if mapped is not None:
            self.mouse = mapped

    def release(self):
        pass

    def take_action(self, pos, button=1):
        for a in reversed(self.actions):
            r = a.get("rect")
            if r and r.collidepoint(pos):
                out = dict(a)
                if out.get("kind") == "minimap":
                    x = clamp(int((pos[0] - r.x) / max(1, r.w) * self.g.map.w), 0, self.g.map.w - 1)
                    y = clamp(int((pos[1] - r.y) / max(1, r.h) * self.g.map.h), 0, self.g.map.h - 1)
                    out["x"], out["y"] = x, y
                    out.pop("rect", None)
                    return out
                out.pop("rect", None)
                return out
        return None

    def hotkey_action(self, key):
        key = str(key).upper()
        if not key:
            return None
        for a in self.actions:
            if a.get("hotkey") == key and a.get("kind") != "minimap":
                out = dict(a)
                out.pop("rect", None)
                return out
        return None

    def on_screen(self, e):
        px, py = self.g.screen_pos(e)
        return -40 <= px <= SCREEN_W + 40 and -40 <= py <= SCREEN_H + 40

    def cycle_subgroup(self):
        groups = self.subgroups()
        if len(groups) > 1:
            self.subgroup = (self.subgroup + 1) % len(groups)
            self.g.select(groups[self.subgroup])

    def subgroups(self):
        groups = []
        by = {}
        for e in self.g.selected():
            if e.is_building:
                key = e.bid
            else:
                key = e.kind
            by.setdefault(key, []).append(e)
        for key, arr in by.items():
            groups.append(arr)
        return groups

    # ---------------------------------------------------------------- screens
    def draw(self, screen):
        self.actions = []
        self.g = self.g
        st = self.g.state
        if st == "title":
            self.draw_title()
        elif st == "skirmish":
            self.draw_title(dim=True)
            self.draw_skirmish()
        elif st == "intro":
            self.draw_intro()
        elif st in ("settings", "controls", "credits") and self.g.state_before == "title":
            self.draw_title(dim=False)
            if st == "settings": self.draw_settings()
            elif st == "controls": self.draw_controls()
            else: self.draw_credits()
        else:
            self.draw_hud()
            if st == "paused":
                self.draw_pause()
            elif st in ("victory", "defeat"):
                self.draw_end(st == "victory")
            elif st == "settings":
                self.draw_settings()
            elif st == "controls":
                self.draw_controls()
            elif st == "credits":
                self.draw_credits()
        # hover detection after actions are built
        self.hover_action = None
        if self.mouse:
            for a in reversed(self.actions):
                r = a.get("rect")
                if r and r.collidepoint(self.mouse):
                    self.hover_action = a
                    break
        if self.hover_action and self.g.state in ("play", "paused"):
            self.draw_tooltip(self.hover_action)

    def draw_title(self, dim=False):
        g = self.g
        if self._grad is None:
            self._grad = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            for y in range(SCREEN_H):
                t = y / SCREEN_H
                a = int(180 * (0.35 + 0.65 * t))
                pygame.draw.line(self._grad, (12, 9, 10, a), (0, y), (SCREEN_W, y))
        g.screen.blit(self._grad, (0, 0))
        if dim:
            s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA); s.fill((8, 7, 9, 140)); g.screen.blit(s, (0, 0))
        if self.logo is None:
            p = os.path.join(ROOT, "assets", "icons", "png", "logo.png")
            try:
                self.logo = pygame.image.load(p).convert_alpha()
            except Exception:
                self.logo = None
        if self.logo:
            lw = 780
            lh = int(self.logo.get_height() * lw / self.logo.get_width())
            im = pygame.transform.smoothscale(self.logo, (lw, lh))
            g.screen.blit(im, (SCREEN_W // 2 - lw // 2, 55))
        else:
            t = self.t("EMBERFALL", 96, PARCH, "display")
            g.screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, 130))
        tag = self.t("A native isometric RTS  ·  deepseek × mimo", 15, PARCH_D, "serif")
        g.screen.blit(tag, (SCREEN_W // 2 - tag.get_width() // 2, 388))
        items = [("Campaign", "campaign"), ("Skirmish", "skirmish"),
                 ("Controls", "controls"), ("Settings", "settings"),
                 ("Credits", "credits"), ("Quit", "quit")]
        for i, (lab, act) in enumerate(items):
            r = pygame.Rect(SCREEN_W // 2 - 170, 424 + i * 52, 340, 44)
            self.button(r, lab, (act, {}), style="wood")
        ver = self.t("v0.9 beta  ·  headless QA  ·  Flare art (CC-BY-SA 3.0)", 12, MUTED, "sans")
        g.screen.blit(ver, (16, SCREEN_H - 22))

    def draw_skirmish(self):
        g = self.g
        r = pygame.Rect(SCREEN_W // 2 - 380, 210, 760, 480)
        self.panel(r, (30, 23, 19), BRASS, 250)
        title = self.t("Choose your war", 34, PARCH, "display")
        g.screen.blit(title, (r.centerx - title.get_width() // 2, r.y + 22))
        desc = self.art.text_wrap("The Hollow Host does not sleep. Pick the pressure you can survive.",
                                  15, 640, PARCH_D)
        g.screen.blit(desc, (r.centerx - 320, r.y + 72))
        for i, (key, d) in enumerate(DIFFICULTY.items()):
            b = pygame.Rect(r.x + 40, r.y + 130 + i * 92, 680, 76)
            hover = b.collidepoint(self.mouse)
            pygame.draw.rect(g.screen, (58, 44, 33) if hover else (42, 32, 25), b, border_radius=6)
            pygame.draw.rect(g.screen, GOLD_L if hover else BRASS, b, 1, border_radius=6)
            n = self.t(d["name"], 22, PARCH, "display")
            g.screen.blit(n, (b.x + 18, b.y + 10))
            bl = self.art.text_wrap(d["blurb"], 14, 620, PARCH_D)
            g.screen.blit(bl, (b.x + 18, b.y + 40))
            self.add(b, kind="menu", action="difficulty", value=key)
        self.button(pygame.Rect(r.x + 40, r.bottom - 54, 150, 38), "Back", ("back", {}))
        self.state = None

    def draw_intro(self):
        g = self.g
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA); s.fill((8, 7, 9, 120)); g.screen.blit(s, (0, 0))
        r = pygame.Rect(SCREEN_W // 2 - 460, 120, 920, 610)
        self.panel(r, (38, 29, 22), BRASS, 252)
        title = self.t("THE ASHEN VALE", 40, PARCH, "display")
        g.screen.blit(title, (r.centerx - title.get_width() // 2, r.y + 26))
        sub = self.t("Emberhold · Year of the Hollow Crown", 15, GOLD, "serif")
        g.screen.blit(sub, (r.centerx - sub.get_width() // 2, r.y + 78))
        lore = ("The crown is broken. The king beneath it is not. "
                "For three nights the Hollow Host has crossed the Ashen Vale, and every farm burns colder than the last. "
                "You are Marshal Aldric, last Ember of the Emberhold. Four workers, a handful of steel, and one hearth. "
                "Raise the hall, wake the vale, and break the Necropolis before the Host drowns it.")
        txt = self.art.text_wrap(lore, 18, 820, PARCH_D, line_gap=5)
        g.screen.blit(txt, (r.centerx - 410, r.y + 112))
        box = pygame.Rect(r.x + 40, r.y + 300, 840, 150)
        self.panel(box, (28, 22, 18), (102, 82, 50), 230)
        o = self.t("OBJECTIVES", 14, GOLD, "display")
        g.screen.blit(o, (box.x + 16, box.y + 12))
        m = self.art.text_wrap("Main: " + OBJECTIVE_MAIN, 17, 790, PARCH)
        g.screen.blit(m, (box.x + 16, box.y + 40))
        b = self.art.text_wrap("Bonus: " + OBJECTIVE_BONUS, 15, 790, PARCH_D)
        g.screen.blit(b, (box.x + 16, box.y + 80))
        tip = self.t("Controls: right-click to move/attack/gather · A attack-move · QWER hero · B build · Esc menu", 13, MUTED, "sans")
        g.screen.blit(tip, (box.x + 16, box.y + 118))
        self.button(pygame.Rect(r.centerx - 140, r.bottom - 76, 280, 46), "Begin the vigil", ("begin", {}), style="wood")
        self.button(pygame.Rect(r.x + 20, r.bottom - 46, 120, 30), "Title", ("title", {}), style="flat")

    def draw_hud(self):
        g = self.g
        w = g.world
        scr = g.screen
        # top bar
        pygame.draw.rect(scr, (24, 18, 15), (0, 0, SCREEN_W, 46))
        pygame.draw.line(scr, BRASS, (0, 46), (SCREEN_W, 46), 2)
        pygame.draw.line(scr, (8, 6, 5), (0, 48), (SCREEN_W, 48), 1)
        self.resource(22, "gold", fmt(w.gold))
        self.resource(158, "lumber", fmt(w.lumber))
        self.resource(294, "food", f"{w.food_used(PLAYER)}/{w.food_max(PLAYER)}")
        timer = self.t(fmt_time(w.time), 18, PARCH, "serif")
        scr.blit(timer, (SCREEN_W // 2 - timer.get_width() // 2, 12))
        diff = self.t(w.diff["name"].upper(), 11, GOLD, "sans")
        scr.blit(diff, (SCREEN_W // 2 - diff.get_width() // 2, 32))
        # objectives / menu
        self.button(pygame.Rect(1198, 8, 158, 30), "Objectives  [O]", ("objectives", {}))
        self.button(pygame.Rect(1364, 8, 116, 30), "Shop  [P]", ("shop", {}))
        self.button(pygame.Rect(1488, 8, 96, 30), "Menu", ("pause", {}))
        # alerts
        y = 58
        for a in w._alerts[-3:]:
            alpha = max(110, int(255 * min(1.0, a["t"] / 0.8)))
            txt = self.t(a["text"], 15, PARCH, "serif")
            pad = 12
            rr = pygame.Rect(SCREEN_W // 2 - txt.get_width() // 2 - pad, y, txt.get_width() + pad * 2, txt.get_height() + 6)
            s = pygame.Surface((rr.w, rr.h), pygame.SRCALPHA); s.fill((20, 15, 12, min(200, alpha)))
            scr.blit(s, rr.topleft)
            pygame.draw.rect(scr, (*GOLD, min(180, alpha)), rr, 1)
            txt.set_alpha(alpha); scr.blit(txt, (rr.x + pad, rr.y + 3))
            y += rr.h + 4
        if self.show_objectives:
            self.draw_objectives()
        # bottom bar
        pygame.draw.rect(scr, (28, 21, 17), (0, 706, SCREEN_W, 194))
        pygame.draw.line(scr, BRASS, (0, 706), (SCREEN_W, 706), 2)
        pygame.draw.line(scr, (10, 8, 7), (0, 708), (SCREEN_W, 708), 1)
        self.draw_selection_panel()
        self.draw_command_card()
        self.draw_center_panel()
        self.draw_minimap()
        if self.shop_open:
            self.draw_shop_panel()
        # autosave hint (not over the purveyor)
        if w.time < 12 and not self.shop_open:
            hint = self.t("Right-click: move / attack / gather   ·   A: attack-move   ·   B: build", 13, PARCH_D, "sans")
            scr.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, 680))

    def resource(self, x, icon, value):
        im = self.icon(icon, 26)
        self.g.screen.blit(im, (x, 9))
        t = self.t(value, 18, PARCH, "serif")
        self.g.screen.blit(t, (x + 32, 12))

    def draw_objectives(self):
        g = self.g; w = g.world
        r = pygame.Rect(1220, 58, 362, 166)
        self.panel(r, (31, 24, 19), BRASS, 242)
        t = self.t("OBJECTIVES", 14, GOLD, "display")
        g.screen.blit(t, (r.x + 14, r.y + 10))
        main = self.art.text_wrap(w.mission["main"], 15, 330, PARCH)
        g.screen.blit(main, (r.x + 14, r.y + 36))
        bon = self.art.text_wrap(w.mission["bonus"], 13, 330, PARCH_D)
        g.screen.blit(bon, (r.x + 14, r.y + 88))
        necro = next((b for b in w.buildings_of(ENEMY) if b.bid == "necropolis"), None)
        if necro:
            self.bar(pygame.Rect(r.x + 14, r.bottom - 26, 334, 12), necro.hp / necro.max_hp, BLOOD)
            lab = self.t("Necropolis", 12, PARCH_D, "sans")
            g.screen.blit(lab, (r.x + 14, r.bottom - 42))
        self.add(pygame.Rect(r.right - 30, r.y + 8, 20, 20), kind="menu", action="objectives")

    def draw_selection_panel(self):
        g = self.g; w = g.world
        sel = g.selected()
        box = pygame.Rect(12, 718, 386, 172)
        self.panel(box, (33, 25, 20), BRASS, 240)
        por = pygame.Rect(20, 726, 148, 148)
        pygame.draw.rect(g.screen, (18, 14, 12), por)
        if sel:
            e = sel[0]
            if e.is_building:
                img, ax, ay = self.art.building(e.bid, e.team, 4)
                sc = min((por.w - 8) / img.get_width(), (por.h - 8) / img.get_height())
                im = pygame.transform.smoothscale(img, (int(img.get_width() * sc), int(img.get_height() * sc)))
                g.screen.blit(im, (por.centerx - im.get_width() // 2, por.centery - im.get_height() // 2 + 6))
            else:
                im = self.art.portrait(e.rig, e.team, por.w - 8)
                g.screen.blit(im, (por.x + 4, por.y + 4))
            pygame.draw.rect(g.screen, BRASS, por, 1)
            name = e.name if hasattr(e, "name") and e.name else \
                (BUILDINGS[e.bid]["name"] if e.is_building else UNITS[e.kind]["name"])
            if e.is_hero:
                name = f"Marshal Aldric  ·  level {e.level}"
            t = self.t(name, 18 if len(name) < 26 else 15, PARCH, "display")
            g.screen.blit(t, (180, 728))
            if e.is_building:
                sub = self.t(("Structure · " + ("Emberhold" if e.team == PLAYER else "Hollow Host")), 12, MUTED, "sans")
            elif e.is_hero:
                sub = self.t("Emberhold · Hero", 12, MUTED, "sans")
            else:
                sub = self.t(("Worker" if e.worker else "Soldier") + " · " + ("Emberhold" if e.team == PLAYER else "Host"), 12, MUTED, "sans")
            g.screen.blit(sub, (180, 750))
            self.bar(pygame.Rect(180, 768, 200, 15), e.hp / max(1, e.max_hp), GREEN)
            hp = self.t(f"{int(e.hp)} / {int(e.max_hp)}", 11, PARCH, "sans")
            g.screen.blit(hp, (184, 768))
            if e.max_mana:
                self.bar(pygame.Rect(180, 786, 200, 10), e.mana / e.max_mana, BLUE)
            if e.is_hero:
                nxt = HERO_LEVELS[min(len(HERO_LEVELS) - 1, e.level)]
                prev = HERO_LEVELS[max(0, e.level - 1)]
                self.bar(pygame.Rect(180, 800, 200, 5), (e.xp - prev) / max(1, nxt - prev), GOLD)
                for i in range(ITEM_SLOTS):
                    rr = pygame.Rect(180 + i * 34, 810, 30, 30)
                    self.draw_item_slot(rr, e.items[i] if i < len(e.items) else None,
                                        i, hero=e)
            else:
                dmg = f"ATK {e.dmg_min}-{e.dmg_max}   ARM {e.armor}"
                dt = self.t(dmg, 12, PARCH_D, "sans")
                g.screen.blit(dt, (180, 802))
            if len(sel) > 1:
                cnt = self.t(f"+{len(sel) - 1} selected", 12, PARCH_D, "sans")
                g.screen.blit(cnt, (180, 824))
            if e.is_building and e.build_progress < 1:
                self.bar(pygame.Rect(180, 824, 200, 8), e.build_progress, GOLD)
        else:
            im = self.icon("emblem", 140)
            g.screen.blit(im, (por.centerx - 70, por.centery - 70))
            t = self.t("No selection", 18, MUTED, "display")
            g.screen.blit(t, (180, 730))
            tip = self.art.text_wrap("Select your workers, then right-click gold and trees. Build farms and a barracks to raise an army.", 13, 190, PARCH_D)
            g.screen.blit(tip, (180, 756))

    def draw_center_panel(self):
        g = self.g; w = g.world
        r = pygame.Rect(668, 714, 690, 180)
        self.panel(r, (31, 24, 19), BRASS, 238)
        title = self.t("THE VALE", 12, GOLD, "display")
        g.screen.blit(title, (r.x + 14, r.y + 9))
        objs = [("Wave", str(getattr(getattr(w, "ai", None), "wave", 0))),
                ("Kills", str(w.stats["kills"])), ("Losses", str(w.stats["losses"])),
                ("Hero", f"lvl {w.hero.level}" if w.hero else "-")]
        for i, (k, v) in enumerate(objs):
            x = r.x + 14 + i * 118
            kt = self.t(k.upper(), 10, MUTED, "sans"); vt = self.t(v, 17, PARCH, "display")
            g.screen.blit(kt, (x, r.y + 30)); g.screen.blit(vt, (x, r.y + 44))
        # objective line
        obj = self.art.text_wrap(w.mission["main"], 12, 420, PARCH_D)
        g.screen.blit(obj, (r.x + 14, r.y + 74))
        # selected group strip
        groups = self.subgroups()
        xx = r.x + 470
        yy = r.y + 30
        for i, grp in enumerate(groups[:4]):
            e = grp[0]
            ic = self.icon(e.bid if e.is_building else e.kind, 28)
            g.screen.blit(ic, (xx, yy))
            n = self.t(str(len(grp)), 12, PARCH, "sans")
            g.screen.blit(n, (xx + 30, yy + 2))
            hp = sum(x.hp for x in grp) / max(1, sum(x.max_hp for x in grp))
            self.bar(pygame.Rect(xx, yy + 30, 66, 4), hp, GREEN)
            xx += 76
        # queue or control groups
        yy = r.y + 92
        if groups and groups[0][0].is_building and groups[0][0].queue:
            b = groups[0][0]
            lab = self.t("Training queue", 11, PARCH_D, "sans")
            g.screen.blit(lab, (r.x + 14, yy))
            for i, q in enumerate(b.queue[:6]):
                ic = self.icon(UNITS[q["type"]]["icon"], 34)
                g.screen.blit(ic, (r.x + 14 + i * 40, yy + 16))
                f = q["progress"] / max(1, q["time"])
                pygame.draw.rect(g.screen, GOLD, (r.x + 14 + i * 40, yy + 50, int(34 * f), 3))
        else:
            lab = self.t("Control groups", 11, PARCH_D, "sans")
            g.screen.blit(lab, (r.x + 14, yy))
            for num in range(1, 7):
                grp = g.control_groups.get(num)
                x = r.x + 14 + (num - 1) * 58
                rr = pygame.Rect(x, yy + 18, 48, 30)
                pygame.draw.rect(g.screen, (40, 31, 24), rr, border_radius=4)
                pygame.draw.rect(g.screen, BRASS if grp else (70, 58, 44), rr, 1, border_radius=4)
                key = self.t(str(num), 12, GOLD if grp else MUTED, "sans")
                g.screen.blit(key, (rr.x + 4, rr.y + 4))
                if grp:
                    ic = self.icon(grp[0].bid if grp[0].is_building else grp[0].kind, 20)
                    g.screen.blit(ic, (rr.x + 20, rr.y + 4))
            # hero ability summary
            h = w.hero
            if h and h.alive:
                ab = self.t("Abilities", 11, PARCH_D, "sans")
                g.screen.blit(ab, (r.x + 14, r.y + 138))
                for i, aid in enumerate(("ember-lance", "aegis", "consecrate", "daybreak")):
                    a = ABILITIES[aid]
                    x = r.x + 80 + i * 46
                    ic = self.icon(a["icon"], 26)
                    if h.level < a["unlock"]:
                        ic = ic.copy(); ic.set_alpha(70)
                    g.screen.blit(ic, (x, r.y + 130))
                    cd = h.abil_cd.get(aid, 0)
                    if cd > 0:
                        cdv = self.t(str(int(math.ceil(cd))), 13, PARCH, "sans")
                        g.screen.blit(cdv, (x + 8, r.y + 134))
        self.add(pygame.Rect(r.x, r.y, r.w, r.h), kind="noop")

    # ---------------------------------------------------------------- items / shop
    def item_state(self, iid, hero=None):
        g = self.g; w = g.world
        hero = hero or w.hero
        it = ITEMS[iid]
        owned = bool(hero) and iid in hero.items
        parts = it.get("parts", [])
        have = sum(1 for p in parts if hero and p in hero.items)
        fee = it.get("cost", {}).get("g", 0)
        ready = (not parts) or have == len(parts)
        return dict(owned=owned, have=have, need=len(parts), fee=fee, ready=ready,
                    afford=w.gold >= fee, in_range=w.shop_in_range(hero),
                    parts=parts)

    def item_lines(self, iid, include_recipe=True):
        it = ITEMS[iid]
        lines = item_stat_lines(iid)
        if include_recipe and it.get("parts"):
            lines.append("Recipe: " + " + ".join(ITEMS[p]["name"] for p in it["parts"]))
        return lines

    def draw_item_slot(self, rect, iid, slot, hero=None):
        g = self.g; w = g.world
        hero = hero or w.hero
        pygame.draw.rect(g.screen, (22, 18, 15), rect, border_radius=4)
        if not iid:
            pygame.draw.rect(g.screen, (62, 51, 40), rect, 1, border_radius=4)
            return
        it = ITEMS[iid]
        pygame.draw.rect(g.screen, GOLD if it.get("active") else BRASS, rect, 1, border_radius=4)
        ic = self.icon(it["icon"], rect.w - 8)
        g.screen.blit(ic, (rect.centerx - ic.get_width() // 2, rect.y + 4))
        cd = hero.item_cd.get(iid, 0) if hero else 0
        if cd > 0:
            ov = pygame.Surface(rect.size, pygame.SRCALPHA)
            ov.fill((8, 8, 12, 165))
            g.screen.blit(ov, rect.topleft)
            t = self.t(str(int(math.ceil(cd))), 14, PARCH, "sans")
            g.screen.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - 8))
        elif it.get("active"):
            pygame.draw.polygon(g.screen, GOLD_L, ((rect.right - 9, rect.y + 4),
                                                   (rect.right - 4, rect.y + 4),
                                                   (rect.right - 4, rect.y + 9)))
        lines = self.item_lines(iid)
        lines.append(f"Sells for {item_sell_value(iid)}g — right-click")
        self.add(rect, kind="slot", slot=slot, label=it["name"], desc=it["desc"], lines=lines)

    def shop_tile(self, rect, iid, hero):
        g = self.g; w = g.world
        st = self.item_state(iid, hero)
        it = ITEMS[iid]
        hover = rect.collidepoint(self.mouse)
        ok = st["ready"] and st["afford"] and not st["owned"]
        pygame.draw.rect(g.screen, (52, 42, 31) if hover else (36, 29, 23), rect, border_radius=5)
        if st["owned"]:
            bd = GREEN
        elif hover and ok:
            bd = GOLD_L
        elif st["ready"] and not st["owned"]:
            bd = GOLD
        else:
            bd = (88, 75, 58)
        pygame.draw.rect(g.screen, bd, rect, 1, border_radius=5)
        ic = self.icon(it["icon"], rect.w - 14)
        if not st["ready"] or st["owned"]:
            ic = ic.copy()
            ic.set_alpha(96 if not st["ready"] else 170)
        g.screen.blit(ic, (rect.centerx - ic.get_width() // 2, rect.y + 6))
        strip = pygame.Rect(rect.x + 1, rect.bottom - 17, rect.w - 2, 16)
        pygame.draw.rect(g.screen, (18, 14, 12), strip, border_radius=3)
        if st["owned"]:
            txt, col = "OWNED", GREEN
        elif st["ready"]:
            txt, col = (f"forge {st['fee']}g" if st["parts"] else f"{st['fee']}g"),                        (GOLD if st["afford"] else (196, 120, 96))
        else:
            txt, col = f"{st['have']}/{st['need']} parts", MUTED
        pt = self.t(txt, 10, col, "sans")
        g.screen.blit(pt, (rect.centerx - pt.get_width() // 2, rect.bottom - 16))
        lines = self.item_lines(iid)
        if st["owned"]:
            lines.append("OWNED — right-click it in the satchel to sell")
        elif st["parts"]:
            names = " + ".join(ITEMS[p]["name"] for p in st["parts"])
            lines.append(f"Forge fee {st['fee']}g — needs {names}")
        else:
            lines.append(f"Price {st['fee']}g")
        lines.append(f"Full tree {item_tree_cost(iid)}g · sells for {item_sell_value(iid)}g")
        self.add(rect, kind="buy", item=iid, label=it["name"], desc=it["desc"],
                 lines=lines)

    def draw_shop_panel(self):
        g = self.g; w = g.world
        hero = w.hero
        r = pygame.Rect(286, 62, 1028, 634)
        self.overlay(96)
        self.panel(r, (30, 23, 18), BRASS, 252)
        title = self.t("THE EMBERHOLD PURVEYOR", 20, GOLD_L, "display")
        g.screen.blit(title, (r.x + 18, r.y + 10))
        sub = self.t("Buy components, then forge them into one stronger item — every stat carries over.",
                     12, PARCH_D, "sans")
        g.screen.blit(sub, (r.x + 18, r.y + 36))
        gi = self.icon("gold", 22)
        g.screen.blit(gi, (r.right - 214, r.y + 17))
        gt = self.t(fmt(w.gold), 20, PARCH, "display")
        g.screen.blit(gt, (r.right - 186, r.y + 14))
        self.button(pygame.Rect(r.right - 116, r.y + 12, 98, 28), "Close [P]", ("shopclose", {}))
        self.line(r.x + 352, r.y + 62, r.x + 352, r.bottom - 16, (92, 74, 50))
        # ---- hero + satchel
        x0, y0 = r.x + 18, r.y + 64
        por = pygame.Rect(x0, y0, 96, 96)
        pygame.draw.rect(g.screen, (18, 14, 12), por)
        if hero:
            im = self.art.portrait(hero.rig, hero.team, 88)
            g.screen.blit(im, (por.centerx - im.get_width() // 2, por.centery - im.get_height() // 2))
        pygame.draw.rect(g.screen, BRASS, por, 1)
        if hero:
            nm = self.t("Marshal Aldric", 18, PARCH, "display")
            g.screen.blit(nm, (x0 + 108, y0))
            sub2 = self.t(f"Emberhold · level {hero.level}", 12, MUTED, "sans")
            g.screen.blit(sub2, (x0 + 108, y0 + 22))
            self.bar(pygame.Rect(x0 + 108, y0 + 42, 140, 15), hero.hp / max(1, hero.max_hp), GREEN)
            hp = self.t(f"{int(hero.hp)}/{int(hero.max_hp)}", 11, PARCH, "sans")
            g.screen.blit(hp, (x0 + 254, y0 + 43))
            self.bar(pygame.Rect(x0 + 108, y0 + 62, 140, 13), hero.mana / max(1, hero.max_mana), BLUE)
            mana = self.t(f"{int(hero.mana)}/{int(hero.max_mana)}", 11, PARCH, "sans")
            g.screen.blit(mana, (x0 + 254, y0 + 61))
            st1 = self.t(f"ATK {hero.dmg_min:.0f}-{hero.dmg_max:.0f}   ARM {hero.armor:.0f}   "
                         f"SPD {hero.cooldown:.2f}s", 11, PARCH_D, "sans")
            g.screen.blit(st1, (x0 + 108, y0 + 78))
            st2 = self.t(f"MOVE {hero.speed:.2f}   REGEN {hero.hp_regen:g} hp/s", 11, PARCH_D, "sans")
            g.screen.blit(st2, (x0 + 108, y0 + 92))
        lab = self.t("SATCHEL", 12, GOLD, "display")
        g.screen.blit(lab, (x0, y0 + 112))
        hint = self.t("left-click an active · right-click to sell", 10, MUTED, "sans")
        g.screen.blit(hint, (x0 + 66, y0 + 114))
        for i in range(ITEM_SLOTS):
            col, row = i % 3, i // 3
            rr = pygame.Rect(x0 + col * 110, y0 + 136 + row * 112, 100, 100)
            iid = hero.items[i] if hero and i < len(hero.items) else None
            self.draw_item_slot(rr, iid, i, hero)
            if iid:
                nm = self.t(ITEMS[iid]["name"], 10, PARCH_D, "sans")
                g.screen.blit(nm, (rr.x, rr.bottom + 2))
        if not w.shop_in_range(hero):
            wr = pygame.Rect(x0, r.bottom - 78, 330, 60)
            self.panel(wr, (70, 30, 26), (176, 84, 72), 244)
            t1 = self.t("OUT OF REACH", 14, (240, 172, 150), "display")
            g.screen.blit(t1, (wr.x + 10, wr.y + 6))
            t2 = self.art.text_wrap("Aldric must stand near the Hall, Keep or Altar of Embers to trade.",
                                    11, 306, PARCH_D)
            g.screen.blit(t2, (wr.x + 10, wr.y + 26))
        # ---- shelves
        x1, yy = r.x + 372, r.y + 64
        cell, step = 92, 106
        for gtitle, ids in SHOP_GROUPS:
            per_row = 6 if len(ids) <= 6 else 4
            gl = self.t(gtitle, 12, GOLD, "display")
            g.screen.blit(gl, (x1, yy))
            yy += 18
            for i, iid in enumerate(ids):
                cx = x1 + (i % per_row) * step
                cy = yy + (i // per_row) * (cell + 22)
                tile = pygame.Rect(cx, cy, cell, cell)
                self.shop_tile(tile, iid, hero)
                nm = self.t(ITEMS[iid]["name"], 10,
                            PARCH if hero and iid in hero.items else PARCH_D, "sans")
                g.screen.blit(nm, (cx + max(0, (cell - nm.get_width()) // 2), cy + cell + 3))
                it = ITEMS[iid]
                for k in range(len(it.get("parts", []))):
                    st = self.item_state(iid, hero)
                    filled = k < st["have"]
                    pygame.draw.circle(g.screen, GOLD if filled else (78, 66, 50),
                                       (cx + 7 + k * 8, cy + 7), 3)
            rows = (len(ids) + per_row - 1) // per_row
            yy += rows * (cell + 22) + 8

    # ---------------------------------------------------------------- commands
    def commands(self):
        g = self.g; w = g.world
        sel = g.selected()
        out = []
        if not sel:
            return out
        first = sel[0]
        if self.build_menu:
            for i, bid in enumerate(BUILD_MENU):
                d = BUILDINGS[bid]
                req = d.get("requires")
                ok = True
                if bid == "keep":
                    ok = any(b.bid == "townhall" and b.build_progress >= 1 for b in w.buildings_of(PLAYER))
                if req and not any(b.bid == req for b in w.buildings_of(PLAYER)):
                    ok = False
                out.append(dict(id="build_" + bid, icon=d["icon"], label=d["name"], hotkey=BASE_KEYS[i],
                                enabled=ok and w.gold >= d["cost"].get("g", 0) and w.lumber >= d["cost"].get("l", 0),
                                kind="build", bid=bid, desc=d["desc"], cost=d["cost"],
                                time=d.get("build_time", 0), req=req))
            out.append(dict(id="back", icon="cancel", label="Back", hotkey="X", kind="buildback", desc="Close the build menu."))
            return out
        if first.is_building:
            b = first
            train = PLAYER_TRAIN.get(b.bid, [])
            for i, ut in enumerate(train):
                d = UNITS[ut]
                req = d.get("requires")
                ok = True
                if req and not any(x.bid == "keep" for x in w.buildings_of(PLAYER)):
                    ok = False
                food_ok = w.food_used(PLAYER) + sum(UNITS[q["type"]]["food"] for q in b.queue) + d["food"] <= w.food_max(PLAYER)
                ok = ok and food_ok and w.gold >= d["cost"].get("g", 0) and w.lumber >= d["cost"].get("l", 0)
                out.append(dict(id="train_" + ut, icon=d["icon"], label=d["name"], hotkey=BASE_KEYS[i],
                                enabled=ok, kind="train", unit=ut, building=b, desc=d["desc"],
                                cost=d["cost"], time=d["build_time"], food=d["food"], req=req))
            research = BUILDINGS[b.bid].get("research", [])
            for j, uid in enumerate(research):
                u = UPGRADES[uid]
                done = uid in w.upgrades
                req = u.get("req_upgrade")
                ok = not done and (not req or req in w.upgrades) and w.gold >= u["cost"].get("g", 0) and w.lumber >= u["cost"].get("l", 0)
                out.append(dict(id="res_" + uid, icon=u["icon"], label=u["name"],
                                hotkey=BASE_KEYS[len(train) + j], enabled=ok and not b.research,
                                kind="research", upgrade=uid, building=b, desc=u["desc"],
                                cost=u["cost"], time=u["time"], done=done))
            if b.bid in ("townhall", "keep", "barracks", "sanctum", "crypt", "slaughterhouse", "temple"):
                out.append(dict(id="rally", icon="rally", label="Rally Point", hotkey="Y", kind="rally",
                                enabled=True, desc="Set where newly trained units gather."))
            if b.queue:
                out.append(dict(id="cancelq", icon="cancel", label="Cancel", hotkey="X", kind="queue_cancel",
                                building=b, enabled=True, desc="Cancel the last unit in the queue."))
            if b.bid == "townhall":
                out.append(dict(id="keep", icon="keep", label="Upgrade to Keep", hotkey="K",
                                kind="research", upgrade="keep", building=b, enabled=False,
                                desc="Requires 300 gold, 180 lumber. Unlocks knights.", cost={"g": 300, "l": 180}))
            return out
        if first.is_hero:
            for aid, a in ABILITIES.items():
                cd = first.abil_cd.get(aid, 0)
                ok = first.level >= a["unlock"] and first.mana >= a["mana"] and cd <= 0
                out.append(dict(id="ab_" + aid, icon=a["icon"], label=a["name"], hotkey=a["hotkey"],
                                enabled=ok, kind="ability", ability=aid, desc=a["desc"], mana=a["mana"],
                                cd=cd, cdmax=a["cooldown"], unlock=a["unlock"]))
            out.append(dict(id="am", icon="attackmove", label="Attack-Move", hotkey="A", kind="attackmove", enabled=True,
                            desc="Move to a point, engaging anything hostile on the way."))
            out.append(dict(id="stop", icon="stop", label="Stop", hotkey="S", kind="stop", enabled=True,
                            desc="Cancel the current order."))
            out.append(dict(id="hold", icon="hold", label="Hold", hotkey="H", kind="hold", enabled=True,
                            desc="Hold position and fight anything in reach."))
            out.append(dict(id="shop", icon="it-bag", label="Purveyor", hotkey="P", kind="shop", enabled=True,
                            desc="The Emberhold purveyor. Buy components, forge them into one stronger item, drink or blink."))
            return out
        if any(u.worker for u in sel):
            out.append(dict(id="build", icon="build", label="Build", hotkey="B", kind="buildmenu", enabled=True,
                            desc="Raise a structure. Farms feed soldiers; barracks train them."))
            out.append(dict(id="gather", icon="gather", label="Gather", hotkey="G", kind="gather", enabled=True,
                            desc="Harvest the nearest gold or lumber."))
            out.append(dict(id="stop", icon="stop", label="Stop", hotkey="S", kind="stop", enabled=True,
                            desc="Cancel the current order."))
            out.append(dict(id="hold", icon="hold", label="Hold", hotkey="H", kind="hold", enabled=True,
                            desc="Hold position."))
            return out
        out.append(dict(id="am", icon="attackmove", label="Attack-Move", hotkey="A", kind="attackmove", enabled=True,
                        desc="Move to a point, engaging anything hostile on the way."))
        out.append(dict(id="stop", icon="stop", label="Stop", hotkey="S", kind="stop", enabled=True,
                        desc="Cancel the current order."))
        out.append(dict(id="hold", icon="hold", label="Hold", hotkey="H", kind="hold", enabled=True,
                        desc="Hold position and fight anything in reach."))
        out.append(dict(id="atk", icon="attack", label="Attack", hotkey="T", kind="attack", enabled=False,
                        desc="Right-click an enemy to attack."))
        return out

    def draw_command_card(self):
        g = self.g; w = g.world
        cmds = self.commands()
        x0, y0 = 406, 722
        cell, gap = 56, 5
        # subgroups
        groups = self.subgroups()
        if len(groups) > 1:
            for i, grp in enumerate(groups[:6]):
                r = pygame.Rect(x0 + i * 44, 698, 40, 20)
                active = grp[0] in g.selection and len(g.selection) == len(grp)
                pygame.draw.rect(g.screen, (58, 45, 33) if active else (34, 27, 21), r, border_radius=3)
                pygame.draw.rect(g.screen, GOLD if active else BRASS, r, 1, border_radius=3)
                ic = self.icon((grp[0].bid if grp[0].is_building else grp[0].kind), 16)
                g.screen.blit(ic, (r.x + 2, r.y + 2))
                n = self.t(str(len(grp)), 11, PARCH, "sans")
                g.screen.blit(n, (r.right - 12, r.y + 2))
                self.add(r, kind="subgroup", index=i)
        for i, c in enumerate(cmds[:12]):
            col, row = i % 4, i // 4
            r = pygame.Rect(x0 + col * (cell + gap), y0 + row * (cell + gap), cell, cell)
            enabled = c.get("enabled", True)
            hover = r.collidepoint(self.mouse)
            pygame.draw.rect(g.screen, (52, 41, 31) if (hover and enabled) else (34, 27, 21), r, border_radius=5)
            pygame.draw.rect(g.screen, GOLD_L if (hover and enabled) else ((96, 80, 54) if enabled else (60, 52, 42)), r, 1, border_radius=5)
            ic = self.icon(c.get("icon", "cancel"), 44)
            if not enabled:
                ic = ic.copy(); ic.set_alpha(105)
            g.screen.blit(ic, (r.centerx - 22, r.y + 5))
            if c.get("hotkey"):
                hk = self.t(c["hotkey"], 11, GOLD if enabled else MUTED, "sans")
                g.screen.blit(hk, (r.right - hk.get_width() - 4, r.bottom - 16))
            if c.get("cd", 0) > 0:
                ov = pygame.Surface((cell, cell), pygame.SRCALPHA); ov.fill((10, 10, 16, 140))
                g.screen.blit(ov, r.topleft)
                cd = self.t(str(int(math.ceil(c["cd"]))), 18, PARCH, "sans")
                g.screen.blit(cd, (r.centerx - cd.get_width() // 2, r.centery - 10))
            if not c.get("enabled", True) and c.get("kind") in ("train", "build", "research"):
                if c.get("cost"):
                    ct = self.t(self.cost(c["cost"]), 10, (206, 120, 96), "sans")
                    g.screen.blit(ct, (r.x + 3, r.y + 2))
            a = dict(c)
            a.pop("building", None)
            a["rect"] = r
            if c.get("building") is not None:
                a["building"] = c["building"]
            self.actions.append(a)
        # queue
        if cmds and cmds[0].get("kind") in ("train", "research", "queue_cancel"):
            pass
        sel = g.selected()
        if sel and sel[0].is_building and sel[0].queue:
            b = sel[0]
            for i, q in enumerate(b.queue[:5]):
                r = pygame.Rect(690 + i * 42, 820, 36, 36)
                pygame.draw.rect(g.screen, (26, 21, 17), r, border_radius=3)
                pygame.draw.rect(g.screen, BRASS, r, 1, border_radius=3)
                ic = self.icon(UNITS[q["type"]]["icon"], 32)
                g.screen.blit(ic, (r.x + 2, r.y + 2))
                f = q["progress"] / max(1, q["time"])
                pygame.draw.rect(g.screen, GOLD, (r.x, r.bottom - 3, int(r.w * f), 3))
            lab = self.t("Training", 12, PARCH_D, "sans")
            g.screen.blit(lab, (690, 804))

    def cost(self, cost):
        parts = []
        if cost.get("g"):
            parts.append(f"{cost['g']}g")
        if cost.get("l"):
            parts.append(f"{cost['l']}l")
        return " ".join(parts)

    # ---------------------------------------------------------------- minimap
    def draw_minimap(self):
        g = self.g; w = g.world
        r = self.minimap_rect
        self.panel(r.inflate(10, 10), (26, 20, 16), BRASS, 245)
        if self._mm_base is None:
            self._mm_base = pygame.transform.smoothscale(g.renderer.minimap_base, (r.w, r.h))
        g.screen.blit(self._mm_base, r.topleft)
        import time as _t
        now = _t.time()
        if self._mm_fog is None or now - self._mm_t > 0.25:
            self._mm_t = now
            fog = pygame.Surface((g.map.w, g.map.h), pygame.SRCALPHA)
            for y in range(g.map.h):
                for x in range(g.map.w):
                    i = y * g.map.w + x
                    if not w.explored[i]:
                        fog.set_at((x, y), (6, 6, 9, 240))
                    elif not w.vis[i]:
                        fog.set_at((x, y), (6, 6, 9, 110))
            self._mm_fog = pygame.transform.smoothscale(fog, (r.w, r.h))
        g.screen.blit(self._mm_fog, r.topleft)
        sx = r.w / g.map.w
        sy = r.h / g.map.h
        for e in w.entities:
            if not e.alive:
                continue
            i = int(e.y) * g.map.w + int(e.x)
            if e.team != PLAYER and not (0 <= i < len(w.explored) and w.explored[i]):
                continue
            col = (226, 180, 84) if e.team == PLAYER else (186, 120, 226) if e.team == ENEMY else (160, 150, 130)
            px, py = r.x + e.x * sx, r.y + e.y * sy
            rad = 3 if e.is_building else 2
            pygame.draw.rect(g.screen, col, (int(px - rad), int(py - rad), rad * 2, rad * 2))
        # camera
        cam = g.camera
        rx = r.x + (cam.x - SCREEN_W / 2) / g.renderer.MW * r.w
        ry = r.y + (cam.y - SCREEN_H / 2) / g.renderer.MH * r.h
        rw = SCREEN_W / g.renderer.MW * r.w
        rh = SCREEN_H / g.renderer.MH * r.h
        pygame.draw.rect(g.screen, (255, 238, 190), (int(rx), int(ry), max(6, int(rw)), max(4, int(rh))), 1)
        self.add(r, kind="minimap")

    # ---------------------------------------------------------------- tooltip
    def draw_tooltip(self, a):
        if a.get("kind") == "minimap":
            return
        g = self.g; w = g.world
        name = a.get("label") or a.get("id", "")
        desc = a.get("desc", "")
        lines = []
        extra = a.get("lines") or []
        if a.get("cost"):
            lines.append(self.cost(a["cost"]) + (f"   {a['time']}s" if a.get("time") else ""))
        if a.get("food"):
            lines.append(f"Food {a['food']}")
        if a.get("mana"):
            lines.append(f"{a['mana']} mana" + (f"   {a.get('cdmax', 0)}s cooldown" if a.get("cdmax") else ""))
        if a.get("req"):
            lines.append("Requires: " + str(a["req"]))
        wide = 330
        dtxt = self.art.text_wrap(desc, 13, wide - 20, PARCH_D) if desc else None
        h = 34 + (dtxt.get_height() if dtxt else 0) + (len(lines) + len(extra)) * 16 + 10
        mx, my = self.mouse
        x = clamp(mx + 18, 0, SCREEN_W - wide - 6)
        y = clamp(my - h - 12, 6, SCREEN_H - h - 6)
        r = pygame.Rect(x, y, wide, h)
        self.panel(r, (24, 19, 16), BRASS, 250)
        if a.get("icon"):
            g.screen.blit(self.icon(a["icon"], 26), (r.x + 8, r.y + 6))
        t = self.t(name, 16, PARCH, "display")
        g.screen.blit(t, (r.x + 40, r.y + 6))
        yy = r.y + 30
        if dtxt:
            g.screen.blit(dtxt, (r.x + 10, yy)); yy += dtxt.get_height() + 2
        for line in lines:
            lt = self.t(line, 12, GOLD if "mana" in line or "Food" in line else PARCH_D, "sans")
            g.screen.blit(lt, (r.x + 10, yy)); yy += 15
        for line in extra:
            col = GOLD_L if line.startswith("+") or line.startswith("Active") else \
                  MUTED if line.startswith(("Recipe", "Full tree", "Sells")) else PARCH_D
            lt = self.t(line, 12, col, "sans")
            g.screen.blit(lt, (r.x + 10, yy)); yy += 16

    # ---------------------------------------------------------------- overlays
    def overlay(self, alpha=150):
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA); s.fill((8, 6, 8, alpha)); self.g.screen.blit(s, (0, 0))

    def draw_pause(self):
        g = self.g
        self.overlay(160)
        r = pygame.Rect(SCREEN_W // 2 - 250, 220, 500, 430)
        self.panel(r, (34, 26, 21), BRASS, 250)
        t = self.t("PAUSED", 38, PARCH, "display")
        g.screen.blit(t, (r.centerx - t.get_width() // 2, r.y + 20))
        sub = self.t("The vale waits.", 14, PARCH_D, "serif")
        g.screen.blit(sub, (r.centerx - sub.get_width() // 2, r.y + 70))
        items = [("Resume", "resume"), ("Restart", "restart"), ("Settings", "settings"),
                 ("Controls", "controls"), ("Quit to Title", "title")]
        for i, (lab, act) in enumerate(items):
            self.button(pygame.Rect(r.x + 70, r.y + 110 + i * 54, 360, 42), lab, (act, {}))

    def draw_end(self, win):
        g = self.g; w = g.world
        self.overlay(180)
        r = pygame.Rect(SCREEN_W // 2 - 380, 150, 760, 560)
        self.panel(r, (30, 23, 19), BRASS, 250)
        title = self.t("THE VALE ENDURES" if win else "THE EMBER FAILS", 42,
                       (240, 200, 120) if win else (200, 100, 90), "display")
        g.screen.blit(title, (r.centerx - title.get_width() // 2, r.y + 22))
        sub = self.t("The Hollow Crown is broken." if win else "The Hollow Crown remembers every grave.", 16, PARCH_D, "serif")
        g.screen.blit(sub, (r.centerx - sub.get_width() // 2, r.y + 80))
        stats = [
            ("Time", fmt_time(w.time)), ("Kills", str(w.stats["kills"])),
            ("Losses", str(w.stats["losses"])), ("Gold gathered", fmt(w.stats["gold_gathered"])),
            ("Lumber gathered", fmt(w.stats["lumber_gathered"])),
            ("Hero level", str(w.hero.level if w.hero else 1)),
        ]
        for i, (k, v) in enumerate(stats):
            col = i % 2; row = i // 2
            x = r.x + 50 + col * 340; y = r.y + 130 + row * 52
            kt = self.t(k, 14, PARCH_D, "sans"); vt = self.t(v, 20, PARCH, "display")
            g.screen.blit(kt, (x, y)); g.screen.blit(vt, (x, y + 18))
        self.button(pygame.Rect(r.centerx - 300, r.bottom - 90, 220, 46), "Fight again", ("restart", {}))
        self.button(pygame.Rect(r.centerx + 80, r.bottom - 90, 220, 46), "Title", ("title", {}))

    def draw_settings(self):
        g = self.g
        self.overlay(150)
        r = pygame.Rect(SCREEN_W // 2 - 280, 200, 560, 400)
        self.panel(r, (34, 26, 21), BRASS, 250)
        t = self.t("SETTINGS", 32, PARCH, "display")
        g.screen.blit(t, (r.centerx - t.get_width() // 2, r.y + 18))
        # sliders
        for i, (label, key) in enumerate((("Music", "music"), ("Sound effects", "sfx"))):
            y = r.y + 100 + i * 80
            lt = self.t(label, 18, PARCH); g.screen.blit(lt, (r.x + 40, y))
            self.button(pygame.Rect(r.x + 250, y, 42, 30), "-", ("vol", {"field": key, "delta": -0.1}))
            self.button(pygame.Rect(r.x + 470, y, 42, 30), "+", ("vol", {"field": key, "delta": 0.1}))
            val = getattr(g.audio, key + "_vol")
            self.bar(pygame.Rect(r.x + 300, y + 10, 160, 12), val, GOLD)
            vt = self.t(str(int(val * 100)) + "%", 14, PARCH_D, "sans")
            g.screen.blit(vt, (r.x + 396, y + 32))
        note = self.art.text_wrap("Headless QA videos and screenshots use the same build. Music and SFX are mixed under the -18 dB bed.", 13, 480, PARCH_D)
        g.screen.blit(note, (r.x + 40, r.y + 270))
        self.button(pygame.Rect(r.centerx - 90, r.bottom - 60, 180, 38), "Back", ("back", {}))

    def draw_controls(self):
        g = self.g
        self.overlay(170)
        r = pygame.Rect(SCREEN_W // 2 - 430, 100, 860, 660)
        self.panel(r, (34, 26, 21), BRASS, 252)
        t = self.t("CONTROLS", 32, PARCH, "display")
        g.screen.blit(t, (r.centerx - t.get_width() // 2, r.y + 18))
        rows = [
            ("Right-click", "Move · attack · gather · set rally"),
            ("Left-drag", "Box select   ·   Shift adds   ·   double-click selects type"),
            ("A", "Attack-move (then click a point)"),
            ("S / H", "Stop / hold position"),
            ("B", "Build menu (workers)  ·  Esc cancels"),
            ("Q W E R", "Hero abilities (Ember Lance, Aegis, Consecrate, Daybreak)"),
            ("1–9 / Ctrl+1–9", "Recall / assign control groups"),
            ("Space", "Center on Marshal Aldric   ·   F1 idle worker"),
            ("O / Esc", "Objectives / pause menu"),
            ("Arrows / edge / MMB", "Pan camera  ·  no WASD command conflicts"),
            ("F11 / Alt+Enter", "Borderless fullscreen"),
        ]
        for i, (k, v) in enumerate(rows):
            y = r.y + 80 + i * 48
            kt = self.t(k, 16, GOLD, "display"); vt = self.t(v, 15, PARCH_D, "serif")
            g.screen.blit(kt, (r.x + 42, y)); g.screen.blit(vt, (r.x + 290, y))
        self.button(pygame.Rect(r.centerx - 90, r.bottom - 58, 180, 36), "Back", ("back", {}))

    def draw_credits(self):
        g = self.g
        self.overlay(170)
        r = pygame.Rect(SCREEN_W // 2 - 430, 100, 860, 660)
        self.panel(r, (34, 26, 21), BRASS, 252)
        t = self.t("CREDITS", 32, PARCH, "display")
        g.screen.blit(t, (r.centerx - t.get_width() // 2, r.y + 18))
        body = ("EMBERFALL — The Hollow Crown\n"
                "A native isometric RTS made in one night by deepseek and mimo.\n\n"
                "Design, simulation, UI and direction: deepseek\n"
                "Audio, QA and art direction: mimo\n\n"
                "Art: Flare (clintbellanger/flare-game) — CC-BY-SA 3.0.\n"
                "Credit: Clint Bellanger and the Flare contributors.\n"
                "Icons: original set drawn for this project.\n\n"
                "Engine: Python 3 + pygame-ce. No web technology.\n"
                "Map: Ashen Vale. 84×84 handcrafted tiles.\n\n"
                "Thank you for waking up and playing it.")
        txt = self.art.text_wrap(body, 16, 760, PARCH_D, line_gap=6)
        g.screen.blit(txt, (r.x + 50, r.y + 78))
        self.button(pygame.Rect(r.centerx - 90, r.bottom - 58, 180, 36), "Back", ("back", {}))
