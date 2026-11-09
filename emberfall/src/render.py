"""Isometric renderer: baked terrain, cliffs, props, sorted entities, fog, lights."""
from __future__ import annotations
import math, random
import pygame
from .core import clamp, lerp, smoothstep, sx, sy, tile_from_screen, Rng
from .defs import *
from .defs import PROJECTILES
from .art import TERRAIN_COL, shade, mix, hexc, SS, radial_glow, soft_shadow
from . import mapgen as MG

TILE = 64
HALF_W, HALF_H = 32, 16


class Camera:
    def __init__(self, x, y, bounds):
        self.x, self.y = float(x), float(y)
        self.bounds = bounds
        self.shake_t = 0.0
        self.shake_power = 0.0
        self.shake_x = self.shake_y = 0

    def update(self, dt):
        if self.shake_t > 0:
            self.shake_t -= dt
            p = max(0.0, self.shake_t) * self.shake_power
            self.shake_x = random.uniform(-p, p)
            self.shake_y = random.uniform(-p, p)
        else:
            self.shake_x = self.shake_y = 0

    def shake(self, power=8.0, duration=0.35):
        self.shake_power = power
        self.shake_t = duration

    def clamp(self):
        x0, y0, x1, y1 = self.bounds
        self.x = clamp(self.x, x0, x1)
        self.y = clamp(self.y, y0, y1)


class Renderer:
    OX = 140 + MAP_H * (TILE // 2)
    OY = 200
    MW = (MAP_W + MAP_H) * (TILE // 2) + 280
    MH = (MAP_W + MAP_H) * (TILE // 2) + 420

    def __init__(self, game):
        self.game = game
        self.map = game.map
        self.art = game.art
        self.surface = pygame.Surface((self.MW, self.MH), pygame.SRCALPHA)
        self.fog_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.dim_veil = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.dim_veil.fill((8, 10, 16, 36))
        self._fog_t = -1.0
        self._fog_cam = (0, 0)
        self.light_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.bake_done = False
        self._tile_big = {}
        self._bake()
        self.minimap_base = self._bake_minimap()
        self.water_tiles = []
        for y in range(self.map.h):
            for x in range(self.map.w):
                if self.map.terr(x, y) == MG.WATER:
                    self.water_tiles.append((x, y))
        self.ember_particles = []
        rng = random.Random(99)
        for i in range(90):
            self.ember_particles.append(dict(
                x=rng.uniform(0, SCREEN_W), y=rng.uniform(0, SCREEN_H),
                vx=rng.uniform(-6, 10), vy=rng.uniform(-14, -4),
                r=rng.uniform(0.6, 2.0), a=rng.uniform(0.15, 0.7),
                ph=rng.uniform(0, 6.28), warm=rng.random() < 0.7))
        self.vignette = self._make_vignette()
        self.dusk = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.dusk.fill((26, 20, 16, 10))

    # ---------------------------------------------------------------- coordinates
    def w2s(self, x, y, h=0):
        return (sx(x, y) + self.OX, sy(x, y, h) + self.OY)

    def screen_to_tile(self, px, py, cam):
        """Approximate tile pick; uses zero-height inverse then asks neighbours."""
        wx = px - SCREEN_W / 2 + cam.x - self.OX
        wy = py - SCREEN_H / 2 + cam.y - self.OY
        tx, ty = tile_from_screen(wx, wy, 0)
        best = (int(math.floor(tx)), int(math.floor(ty)))
        return best

    def cam_bounds(self):
        return (SCREEN_W / 2 + 10, SCREEN_H / 2 + 10,
                self.MW - SCREEN_W / 2 - 10, self.MH - SCREEN_H / 2 - 10)

    # ---------------------------------------------------------------- terrain bake
    def _bake(self):
        m = self.map
        s = self.surface
        s.fill((25, 22, 24, 255))
        OX, OY = self.OX, self.OY
        # pass 1: opaque ground base (kills alpha seams without covering texture)
        for d in range(m.w + m.h - 1):
            for x in range(max(0, d - m.h + 1), min(m.w - 1, d) + 1):
                y = d - x
                h = m.height[y * m.w + x]
                terr = m.terr(x, y)
                v = (x * 7 + y * 13 + h * 3) % 10
                cxp = sx(x, y) + OX
                cyp = sy(x, y, h) + OY
                base = getattr(self.art, "terrain_avg", {}).get(terr, TERRAIN_COL[terr])
                base = shade(base, 1.0)
                pygame.draw.polygon(s, base, [(int(cxp), int(cyp - 18)), (int(cxp + 34), int(cyp + 16)),
                                              (int(cxp), int(cyp + 34)), (int(cxp - 34), int(cyp + 16))])
        # pass 2: painterly textures
        for d in range(m.w + m.h - 1):
            for x in range(max(0, d - m.h + 1), min(m.w - 1, d) + 1):
                y = d - x
                h = m.height[y * m.w + x]
                terr = m.terr(x, y)
                if terr == MG.WATER:
                    continue
                v = (x * 7 + y * 13 + h * 3) % 10
                key = (terr, v)
                big = self._tile_big.get(key)
                if big is None:
                    big = pygame.transform.smoothscale(self.art.tiles[key], (70, 38))
                    self._tile_big[key] = big
                px = sx(x, y) + OX - 35
                py = sy(x, y, h) + OY - 3
                s.blit(big, (int(px), int(py)))
        # forest floor shadows under the tree line
        for (x, y) in m.wood:
            hgt = m.height_at(x, y)
            cx, cy = sx(x + 0.5, y + 0.5) + OX, sy(x + 0.5, y + 0.5, hgt) + OY + 3
            sh = pygame.Surface((52, 22), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (10, 14, 10, 66), (0, 0, 52, 22))
            s.blit(sh, (int(cx - 26), int(cy - 8)))
        # cliffs and banks
        for y in range(m.h):
            for x in range(m.w):
                self._draw_cliffs(s, x, y)
        # decals to break the tile grid
        rng = random.Random(4242)
        for _ in range(700):
            x = rng.randrange(3, m.w - 3); y = rng.randrange(3, m.h - 3)
            terr = m.terr(x, y)
            if terr in (MG.WATER, MG.ROCK):
                continue
            h = m.height_at(x, y)
            cx = sx(x + rng.random(), y + rng.random()) + OX
            cy = sy(x + rng.random(), y + rng.random(), h) + OY + 5
            col = (52, 74, 44) if terr in (MG.GRASS, MG.MOSS) else (96, 76, 54)
            rad = rng.randint(10, 34)
            dec = pygame.Surface((rad * 2, rad), pygame.SRCALPHA)
            pygame.draw.ellipse(dec, (*col, rng.randint(14, 30)), (0, 0, rad * 2, rad))
            s.blit(dec, (int(cx - rad), int(cy - rad // 2)))
        # shoreline foam
        for y in range(m.h):
            for x in range(m.w):
                if m.terr(x, y) != MG.WATER:
                    continue
                for dx, dy, a, b in ((1, 0, (x + 1, y), (x + 1, y + 1)),
                                     (0, 1, (x + 1, y + 1), (x, y + 1))):
                    nx, ny = x + dx, y + dy
                    if not m.inb(nx, ny) or m.terr(nx, ny) == MG.WATER:
                        continue
                    p1 = (sx(*a) + OX, sy(*a, 0) + OY)
                    p2 = (sx(*b) + OX, sy(*b, 0) + OY)
                    pygame.draw.line(s, (198, 214, 204, 105), p1, p2, 2)
                    pygame.draw.line(s, (150, 190, 186, 60),
                                     (p1[0], p1[1] + 3), (p2[0], p2[1] + 3), 2)
        # macro paint pass to break the tile lattice into a continuous field
        ov = self.art.ground_overlay()
        step = 512
        for y0 in range(0, self.MH, step):
            for x0 in range(0, self.MW, step):
                s.blit(ov, (x0, y0))
        # warm late-afternoon grade
        s.fill((26, 24, 14), special_flags=pygame.BLEND_RGB_ADD)
        self.bake_done = True

    def _draw_cliffs(self, s, x, y):
        m = self.map
        h = m.height_at(x, y)
        if h <= 0:
            return
        faces = ((1, 0, ((x + 1, y), (x + 1, y + 1)), 1.14),
                 (0, 1, ((x + 1, y + 1), (x, y + 1)), 0.92))
        for dx, dy, (a, b), lit in faces:
            nx, ny = x + dx, y + dy
            nh = m.height_at(nx, ny)
            if nh >= h:
                continue
            dh = h - nh
            p1 = (sx(*a) + self.OX, sy(*a, h) + self.OY)
            p2 = (sx(*b) + self.OX, sy(*b, h) + self.OY)
            q1 = (p1[0], sy(*a, nh) + self.OY)
            q2 = (p2[0], sy(*b, nh) + self.OY)
            terr = m.terr(x, y)
            base = (100, 94, 84) if terr != MG.SAND else (156, 138, 100)
            if m.terr(nx, ny) == MG.WATER:
                base = (122, 106, 78)
            col = shade(base, (0.94 + 0.1 * ((x * 3 + y) % 3)) * lit)
            pts = [(p1[0], p1[1]), (p2[0], p2[1]), (p2[0], q2[1]), (p1[0], q1[1])]
            pygame.draw.polygon(s, col, pts)
            # top lip
            pygame.draw.line(s, shade(col, 1.28), p1, p2, 2)
            is_ramp = bool(m.ramp[y * m.w + x] or m.ramp[ny * m.w + nx])
            if is_ramp:
                steps = max(3, dh * 3)
                for k in range(1, steps):
                    t = k / steps
                    y1 = p1[1] + (q1[1] - p1[1]) * t
                    y2 = p2[1] + (q2[1] - p2[1]) * t
                    pygame.draw.line(s, shade(col, 1.18 if k % 2 else 0.78), (p1[0] + 2, y1), (p2[0], y2), 2)
                pygame.draw.polygon(s, (0, 0, 0, 28), [pts[2], pts[3], (pts[0][0], pts[0][1] + 3)])
            else:
                # strata + cracks
                for k in range(1, 4):
                    t = k / 4
                    y1 = p1[1] + (q1[1] - p1[1]) * t + 1
                    y2 = p2[1] + (q2[1] - p2[1]) * t + 1
                    pygame.draw.line(s, shade(col, 0.7), (p1[0], y1), (p2[0], y2), 1)
                for k in range(1, 4):
                    t = k / 4 + 0.06
                    x0 = p1[0] + (p2[0] - p1[0]) * t
                    ya = p1[1] + (p2[1] - p1[1]) * t
                    yb = q1[1] + (q2[1] - q1[1]) * t
                    pygame.draw.line(s, shade(col, 0.78), (x0, ya), (x0 + 2, yb), 1)
                pygame.draw.line(s, shade(col, 0.5), q1, q2, 2)
                # soft contact shadow on lower ground
                sh = pygame.Surface((int(abs(p2[0] - p1[0])) + 10, 8), pygame.SRCALPHA)
                pygame.draw.ellipse(sh, (12, 10, 12, 60), (0, 0, sh.get_width(), sh.get_height()))
                s.blit(sh, (int(min(p1[0], p2[0])) - 5, int(max(q1[1], q2[1])) - 2))

    def _bake_minimap(self):
        m = self.map
        surf = pygame.Surface((m.w * 3, m.h * 3), pygame.SRCALPHA)
        for y in range(m.h):
            for x in range(m.w):
                c = TERRAIN_COL[m.terr(x, y)]
                h = m.height_at(x, y)
                c = shade(c, 1.0 + (h - 1) * 0.12)
                if m.road[y * m.w + x]:
                    c = mix(c, (152, 124, 88), 0.4)
                pygame.draw.rect(surf, c, (x * 3, y * 3, 3, 3))
        for (x, y) in m.wood:
            pygame.draw.rect(surf, (32, 54, 34), (x * 3, y * 3, 3, 3))
        for mine in m.mines:
            pygame.draw.rect(surf, (226, 186, 74), ((mine["x"] - 1) * 3, (mine["y"] - 1) * 3, 6, 6))
        for y in range(m.h):
            for x in range(m.w):
                if m.ford[y * m.w + x]:
                    pygame.draw.rect(surf, (120, 214, 214), (x * 3, y * 3, 3, 3))
        return surf

    def _make_vignette(self):
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        cx, cy = SCREEN_W / 2, SCREEN_H / 2
        for i in range(22):
            t = i / 22
            a = int(5 + 28 * t * t)
            pygame.draw.rect(s, (6, 5, 8, a),
                             (int(i * 10), int(i * 7), SCREEN_W - i * 20, SCREEN_H - i * 14), 12)
        return s

    # ---------------------------------------------------------------- draw
    def draw(self, screen, game, cam, time):
        screen.fill((18, 16, 20))
        vx = int(cam.x - SCREEN_W / 2)
        vy = int(cam.y - SCREEN_H / 2)
        sx0 = clamp(vx, 0, self.MW); sy0 = clamp(vy, 0, self.MH)
        r = pygame.Rect(sx0, sy0, min(SCREEN_W, self.MW - sx0), min(SCREEN_H, self.MH - sy0))
        screen.blit(self.surface, (0, 0), r)
        # water shimmer + readable fords
        self._draw_water(screen, cam, time)
        self._draw_fords(screen, cam, time)
        # selection ground markers
        self._draw_ground_markers(screen, game, cam, time)
        # gather drawables, culled to the camera's tile neighbourhood
        draws = []
        m = self.map
        corners = [tile_from_screen(cam.x - SCREEN_W / 2 - self.OX, cam.y - SCREEN_H / 2 - self.OY, 0),
                   tile_from_screen(cam.x + SCREEN_W / 2 - self.OX, cam.y - SCREEN_H / 2 - self.OY, 0),
                   tile_from_screen(cam.x - SCREEN_W / 2 - self.OX, cam.y + SCREEN_H / 2 - self.OY, 2),
                   tile_from_screen(cam.x + SCREEN_W / 2 - self.OX, cam.y + SCREEN_H / 2 - self.OY, 2)]
        tx0 = min(c[0] for c in corners) - 5; tx1 = max(c[0] for c in corners) + 5
        ty0 = min(c[1] for c in corners) - 5; ty1 = max(c[1] for c in corners) + 5
        for p in m.props:
            if p.get("gone") or p["x"] < tx0 or p["x"] > tx1 or p["y"] < ty0 or p["y"] > ty1:
                continue
            draws.append((p["x"] + p["y"], 1, p))
        for e in game.entities:
            if not e.alive and e.death_t > 2.5:
                continue
            draws.append((e.x + e.y, 0, e))
        draws.sort(key=lambda d: (d[0], d[1]))
        for depth, kind, obj in draws:
            if kind == 1:
                self._draw_prop(screen, obj, cam, time)
            else:
                if not self._entity_visible(obj, game):
                    continue
                if obj.is_building:
                    self._draw_building(screen, obj, cam, time)
                else:
                    self._draw_unit(screen, obj, cam, time)
        self._draw_projectiles(screen, game, cam)
        self._draw_particles(screen, game, cam)
        self._draw_health_bars(screen, game, cam)
        # fog
        self._draw_fog(screen, game, cam, time)
        # lighting
        self._draw_lights(screen, game, cam, time)
        # placement ghost
        self._draw_placement(screen, game, cam)
        self._draw_cursor_effects(screen, game, cam, time)
        # atmosphere
        screen.blit(self.dusk, (0, 0))
        self._draw_embers(screen, game, cam, time)
        screen.blit(self.vignette, (0, 0))
        if game.debug:
            self._draw_debug(screen, game, cam)

    def screen_to_world_bounds(self, cam):
        # rough tile bounds of the viewport
        wx = cam.x - self.OX
        wy = cam.y - self.OY
        tx, ty = tile_from_screen(wx, wy, 1)
        return (tx - 30, ty - 30)

    def _entity_visible(self, e, game):
        if e.team == PLAYER or self.game.mode in ("menu", "intro"):
            return True
        tx, ty = int(e.x), int(e.y)
        if not self.map.inb(tx, ty):
            return True
        i = ty * self.map.w + tx
        return bool(game.vis[i])

    def _draw_prop(self, screen, p, cam, time):
        kind = p["kind"]
        if p.get("gone"):
            return
        frame = 0
        if kind in ("tree", "pine", "dead"):
            frame = int(time * (0.55 + 0.12 * p.get("sway", 1.0)) + p.get("phase", 0)) % 3
        elif kind == "fire":
            frame = int(time * 9 + p.get("phase", 0)) % 3
        h = self.map.height_at(int(p["x"]), int(p["y"]))
        px, py = self.w2s(p["x"], p["y"], h)
        px -= cam.x - SCREEN_W / 2
        py -= cam.y - SCREEN_H / 2
        if px < -170 or px > SCREEN_W + 170 or py < -220 or py > SCREEN_H + 170:
            return
        img, ax, ay = self.art.prop(kind, p.get("variant", 0), frame, p.get("scale", 1.0))
        screen.blit(img, (int(px - ax), int(py - ay)))

    def _draw_unit(self, screen, e, cam, time):
        # animation frame selection
        frames = {"idle": 2, "walk": 4, "attack": 4, "cast": 3, "death": 5, "gather": 3, "ride": 4}
        n = frames.get(e.anim, 2)
        frame = int(e.anim_t * n * 4) % n
        if e.anim == "death":
            frame = min(4, int(e.anim_t * 5))
        img, ax, ay = self.art.unit(e.rig, e.facing_bucket, e.anim if e.alive else "death", frame, e.team)
        px, py = self.w2s(e.x, e.y, e.height)
        px -= cam.x - SCREEN_W / 2
        py -= cam.y - SCREEN_H / 2
        if not e.alive:
            img = img.copy()
            img.set_alpha(max(0, int(255 * (1 - (e.death_t - 1.5) / 2.5))))
        screen.blit(img, (int(px - ax), int(py - ay)))
        # carried resource
        if getattr(e, "carry", 0) > 0:
            pygame.draw.circle(screen, (228, 188, 78), (int(px + 10), int(py - 48)), 4)
            pygame.draw.circle(screen, (60, 46, 24), (int(px + 10), int(py - 48)), 4, 1)

    def _draw_building(self, screen, e, cam, time):
        progress = e.build_progress
        stage = 4 if progress >= 1 else int(progress * 4)
        img, ax, ay = self.art.building(e.bid, e.team, stage)
        px, py = self.w2s(e.x + e.bw / 2, e.y + e.bh / 2, e.height)
        px -= cam.x - SCREEN_W / 2
        py -= cam.y - SCREEN_H / 2
        screen.blit(img, (int(px - ax), int(py - ay)))
        if progress < 1:
            # scaffolding shimmer + progress bar
            w = 56
            pygame.draw.rect(screen, (24, 20, 18), (int(px - w / 2), int(py - ay - 10), w, 5), border_radius=2)
            pygame.draw.rect(screen, (214, 166, 72), (int(px - w / 2), int(py - ay - 10), int(w * progress), 5), border_radius=2)
            for i in range(3):
                bob = math.sin(time * 2 + i * 2.1) * 2
                pygame.draw.line(screen, (120, 96, 62), (int(px - 34 + i * 28), int(py + bob)), (int(px - 30 + i * 28), int(py - 50)), 2)
        if e.bid in ("tower", "bonetower") and progress >= 1:
            # pennant
            top = py - ay + 6
            pygame.draw.line(screen, (70, 56, 40), (int(px), int(top)), (int(px), int(top - 22)), 2)
            col = TEAM_COLORS[e.team]["light"]
            pts = [(px, top - 22), (px + 16 + math.sin(time * 3) * 2, top - 17), (px, top - 11)]
            pygame.draw.polygon(screen, hexc(col), [(int(a), int(b)) for a, b in pts])

    def _draw_ground_markers(self, screen, game, cam, time):
        for e in game.entities:
            if not e.selected or not e.alive:
                continue
            px, py = self.w2s(e.x, e.y, e.height)
            px -= cam.x - SCREEN_W / 2
            py -= cam.y - SCREEN_H / 2
            if e.is_building:
                w = e.bw * TILE
                pygame.draw.ellipse(screen, (255, 214, 120, 60), (int(px - w / 2), int(py - 22), w, 44), 0)
            else:
                pygame.draw.ellipse(screen, (255, 216, 128), (int(px - 15), int(py - 8), 30, 13), 2)
                pygame.draw.ellipse(screen, (20, 16, 12), (int(px - 13), int(py - 6), 26, 9), 1)

    def _draw_projectiles(self, screen, game, cam):
        for p in game.projectiles:
            px, py = self.w2s(p["x"], p["y"], p.get("z", 1))
            px -= cam.x - SCREEN_W / 2
            py -= cam.y - SCREEN_H / 2
            col = PROJECTILES.get(p.get("type"), PROJECTILES["arrow"])["color"]
            pygame.draw.circle(screen, col, (int(px), int(py)), 2)
            pygame.draw.line(screen, col, (int(px), int(py)), (int(px - 3), int(py - 3)), 1)

    def _draw_particles(self, screen, game, cam):
        for p in game.particles:
            px, py = self.w2s(p["x"], p["y"], p["z"])
            px -= cam.x - SCREEN_W / 2
            py -= cam.y - SCREEN_H / 2
            a = max(0, int(255 * p["life"] / p["max_life"]))
            r = max(1, int(p["r"]))
            if p.get("glow"):
                s = self.art.glow_sprite(p["color"], int(max(6, p["r"] * 3)), 120)
                s.set_alpha(a)
                screen.blit(s, (int(px - s.get_width() / 2), int(py - s.get_height() / 2)))
            else:
                surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(surf, (*p["color"], a), (r, r), r)
                screen.blit(surf, (int(px - r), int(py - r)))

    def _draw_health_bars(self, screen, game, cam):
        for e in game.entities:
            if not e.alive or e.is_building:
                continue
            if e.hp >= e.max_hp and not e.selected:
                continue
            if not self._entity_visible(e, game):
                continue
            px, py = self.w2s(e.x, e.y, e.height)
            px -= cam.x - SCREEN_W / 2
            py -= cam.y - SCREEN_H / 2
            w = 30 if not e.is_hero else 44
            y = int(py - 56)
            pygame.draw.rect(screen, (18, 14, 12), (int(px - w / 2) - 1, y - 1, w + 2, 6), border_radius=2)
            frac = clamp(e.hp / e.max_hp, 0, 1)
            col = (96, 190, 92) if frac > 0.55 else (224, 186, 72) if frac > 0.28 else (196, 74, 58)
            pygame.draw.rect(screen, col, (int(px - w / 2), y, int(w * frac), 4), border_radius=1)
            if e.is_hero:
                pygame.draw.rect(screen, (86, 130, 214), (int(px - w / 2), y + 5, int(w * clamp(e.mana / e.max_mana, 0, 1)), 2))

    def _draw_fog(self, screen, game, cam, time0=0):
        m = self.map
        # one uniform dimming veil (no per-tile alpha seams), then opaque unexplored
        screen.blit(self.dim_veil, (0, 0))
        moved = abs(cam.x - self._fog_cam[0]) + abs(cam.y - self._fog_cam[1]) > 2
        if not moved and abs(time0 - self._fog_t) < 0.18:
            screen.blit(self.fog_surf, (0, 0))
            return
        self._fog_cam = (cam.x, cam.y)
        self._fog_t = time0
        self.fog_surf.fill((0, 0, 0, 0))
        left = cam.x - SCREEN_W / 2
        top = cam.y - SCREEN_H / 2
        # visible tile range via four corners
        corners = [tile_from_screen(cam.x - SCREEN_W / 2 - self.OX, cam.y - SCREEN_H / 2 - self.OY, 0),
                   tile_from_screen(cam.x + SCREEN_W / 2 - self.OX, cam.y - SCREEN_H / 2 - self.OY, 0),
                   tile_from_screen(cam.x - SCREEN_W / 2 - self.OX, cam.y + SCREEN_H / 2 - self.OY, 2),
                   tile_from_screen(cam.x + SCREEN_W / 2 - self.OX, cam.y + SCREEN_H / 2 - self.OY, 2)]
        tx0 = int(min(c[0] for c in corners)) - 4; tx1 = int(max(c[0] for c in corners)) + 4
        ty0 = int(min(c[1] for c in corners)) - 4; ty1 = int(max(c[1] for c in corners)) + 4
        for y in range(max(0, ty0), min(m.h, ty1 + 1)):
            for x in range(max(0, tx0), min(m.w, tx1 + 1)):
                i = y * m.w + x
                if game.explored[i]:
                    continue
                h = m.height[i]
                px, py = self.w2s(x, y, h)
                px -= left; py -= top
                if px < -80 or px > SCREEN_W + 80 or py < -60 or py > SCREEN_H + 60:
                    continue
                px, py = int(round(px)), int(round(py))
                pts = [(px, py - 1), (px + 33, py + 16), (px, py + 33), (px - 33, py + 16)]
                pygame.draw.polygon(self.fog_surf, (6, 6, 9, 255), pts)
        screen.blit(self.fog_surf, (0, 0))

    def _draw_lights(self, screen, game, cam, time):
        self.light_surf.fill((0, 0, 0, 0))
        left = cam.x - SCREEN_W / 2
        top = cam.y - SCREEN_H / 2
        lights = []
        for p in self.map.props:
            if p["kind"] == "fire":
                lights.append((p["x"], p["y"], 34, (255, 148, 70), 0.4))
        for e in game.entities:
            if not e.alive:
                continue
            if e.is_building:
                if e.bid in ("townhall", "keep", "necropolis", "sanctum", "temple", "altar", "altarhollow"):
                    lights.append((e.x + e.bw / 2, e.y + e.bh / 2, 34 if e.bid in ("townhall", "keep", "necropolis") else 26,
                                   (255, 170, 90) if e.team == PLAYER else (150, 120, 230), 0.16))
            elif e.is_hero:
                lights.append((e.x, e.y, 36, (255, 190, 120), 0.3))
        for (x, y, rad, col, strength) in lights:
            h = self.map.height_at(int(x), int(y))
            px, py = self.w2s(x, y, h)
            px -= left; py -= top
            if px < -rad or px > SCREEN_W + rad or py < -rad or py > SCREEN_H + rad:
                continue
            img = self.art.glow_sprite(col, rad, int(90 * strength))
            self.light_surf.blit(img, (int(px - rad), int(py - rad - 10)), special_flags=pygame.BLEND_ADD)
        screen.blit(self.light_surf, (0, 0), special_flags=pygame.BLEND_ADD)

    def _draw_embers(self, screen, game, cam, time):
        for p in self.ember_particles:
            x = (p["x"] + p["vx"] * time + math.sin(time * 0.7 + p["ph"]) * 12) % (SCREEN_W + 40) - 20
            y = (p["y"] + p["vy"] * time) % (SCREEN_H + 40) - 20
            a = int(255 * p["a"] * (0.55 + 0.45 * math.sin(time * 2 + p["ph"])))
            col = (255, 150, 80) if p["warm"] else (150, 190, 200)
            s = pygame.Surface((int(p["r"] * 4), int(p["r"] * 4)), pygame.SRCALPHA)
            pygame.draw.circle(s, (*col, max(0, a)), (int(p["r"] * 2), int(p["r"] * 2)), max(1, int(p["r"])))
            screen.blit(s, (int(x), int(y)), special_flags=pygame.BLEND_ADD)

    def _draw_placement(self, screen, game, cam):
        p = game.placement
        if not p:
            return
        art = self.art.building(p["bid"], PLAYER, 4)
        img, ax, ay = art
        tx, ty = game.mouse_tile
        bw, bh = BUILDINGS[p["bid"]]["size"]
        valid = game.placement_valid(tx, ty)
        px, py = self.w2s(tx + bw / 2, ty + bh / 2, self.map.height_at(tx, ty))
        px -= cam.x - SCREEN_W / 2
        py -= cam.y - SCREEN_H / 2
        img = img.copy()
        img.set_alpha(150)
        screen.blit(img, (int(px - ax), int(py - ay)))
        overlay = pygame.Surface((bw * TILE, bh * TILE), pygame.SRCALPHA)
        col = (110, 220, 110, 42) if valid else (220, 80, 70, 54)
        pygame.draw.polygon(overlay, col, [(bw * 32, 0), (bw * 64, bh * 16), (bw * 32, bh * 32), (0, bh * 16)])
        screen.blit(overlay, (int(px - bw * 32), int(py - bh * 16 + 16)))

    def _draw_cursor_effects(self, screen, game, cam, time):
        if game.drag_start and game.drag_now:
            x0, y0 = game.drag_start; x1, y1 = game.drag_now
            r = pygame.Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
            pygame.draw.rect(screen, (150, 210, 140, 40), r, 0)
            pygame.draw.rect(screen, (200, 236, 170), r, 1)
        if game.attack_move_mode or game.targeting:
            mx, my = pygame.mouse.get_pos()
            col = (255, 150, 90) if game.targeting else (240, 200, 110)
            pygame.draw.circle(screen, col, (mx, my), 9, 2)
            pygame.draw.line(screen, col, (mx - 14, my), (mx - 5, my), 2)
            pygame.draw.line(screen, col, (mx + 5, my), (mx + 14, my), 2)
            pygame.draw.line(screen, col, (mx, my - 14), (mx, my - 5), 2)
            pygame.draw.line(screen, col, (mx, my + 5), (mx, my + 14), 2)

    def _draw_fords(self, screen, cam, time):
        m = self.map
        left = cam.x - SCREEN_W / 2; top = cam.y - SCREEN_H / 2
        for y in range(m.h):
            for x in range(m.w):
                if not m.ford[y * m.w + x]:
                    continue
                px, py = self.w2s(x + 0.5, y + 0.5, m.height_at(x, y))
                px -= left; py -= top
                if px < -40 or px > SCREEN_W + 40 or py < -40 or py > SCREEN_H + 40:
                    continue
                pygame.draw.polygon(screen, (92, 180, 186, 46),
                                    [(int(px), int(py) - 8), (int(px) + 26, int(py) + 5),
                                     (int(px), int(py) + 18), (int(px) - 26, int(py) + 5)])
                if math.sin(time * 1.6 + x) > 0.62:
                    pygame.draw.line(screen, (210, 240, 238, 120), (int(px - 12), int(py + 2)), (int(px + 8), int(py - 4)), 1)

    def _draw_water(self, screen, cam, time):
        left = cam.x - SCREEN_W / 2
        top = cam.y - SCREEN_H / 2
        for (x, y) in self.water_tiles:
            h = 0
            px, py = self.w2s(x + 0.5, y + 0.5, h)
            px -= left; py -= top
            if px < -64 or px > SCREEN_W + 64 or py < -40 or py > SCREEN_H + 40:
                continue
            ph = time * 1.3 + x * 0.7 + y * 0.9
            a = int(26 + 30 * (0.5 + 0.5 * math.sin(ph)))
            pygame.draw.line(screen, (170, 216, 210, a),
                             (int(px - 12 + math.sin(ph) * 4), int(py)), (int(px + 2 + math.sin(ph) * 4), int(py)), 1)

    def _draw_debug(self, screen, game, cam):
        f = self.art.font(14, "sans")
        lines = [f"fps {game.fps:.0f}  ents {len(game.entities)}  vis {sum(game.vis)}",
                 f"cam {int(cam.x)},{int(cam.y)}  sel {len(game.selection)}  mode {game.mode}"]
        for i, line in enumerate(lines):
            screen.blit(f.render(line, True, (230, 230, 200)), (10, 10 + i * 16))
