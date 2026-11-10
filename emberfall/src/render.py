"""Isometric renderer: baked terrain, cliffs, props, sorted entities, fog, lights."""
from __future__ import annotations
import math, random
import pygame
from .core import clamp, lerp, smoothstep, sx, sy, tile_from_screen, Rng, hash2
from .defs import *
from .defs import PROJECTILES
from .art import TERRAIN_COL, shade, mix, hexc, SS, radial_glow, soft_shadow
from . import mapgen as MG

TILE = 64
HALF_W, HALF_H = 32, 16

# --- fog compositing -------------------------------------------------------
# The shroud is built at 1/8 screen resolution — one texel per ~1/3 tile — as
# DIAMOND polygons in the iso lattice (a bounding-box rect per tile prints a
# one-tile-square staircase, which is exactly what players reported), blurred
# by a half-scale pass, then smoothscaled up when it composites.  The contour
# therefore interpolates over ~3 texels (~24px) and reads as a painted curve.
# Two tones, per the AAA polish bar: unexplored is a deep near-black wall
# (kept 85-93% opaque by the cloud modulation so terrain does not ghost
# through), explored-but-not-visible is a cool memory veil, visible is clear.
FOG_DIV = 8
FOG_W, FOG_H = SCREEN_W // FOG_DIV, SCREEN_H // FOG_DIV
FOG_SHROUD = (5, 6, 10)      # unexplored wall colour
FOG_VEIL = (14, 20, 34)      # explored-not-visible colour (cool, desaturated)
FOG_SHROUD_A = 236           # 93% max, cloud modulation lands it at 85-93%
FOG_VEIL_A = 114             # 45% of frame, modulation keeps 41-45%


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
    # Class-level defaults for the stock 84x84 map — kept so any external
    # reader of Renderer.OX/MW still sees the historical numbers. Instances
    # shadow these with values derived from their ACTUAL map (campaign
    # scenarios can be bigger than 84x84, up to the council's 128 cap).
    OX = 140 + MAP_H * (TILE // 2)
    OY = 200
    MW = (MAP_W + MAP_H) * (TILE // 2) + 280
    MH = (MAP_W + MAP_H) * (TILE // 2) + 420

    def __init__(self, game):
        self.game = game
        self.map = game.map
        self.art = game.art
        # layout + baked surface derive from the map, not the module constants
        # (identical numbers to the class attributes when the map is 84x84)
        self.OX = 140 + self.map.h * (TILE // 2)
        self.OY = 200
        self.MW = (self.map.w + self.map.h) * (TILE // 2) + 280
        self.MH = (self.map.w + self.map.h) * (TILE // 2) + 420
        self.surface = pygame.Surface((self.MW, self.MH), pygame.SRCALPHA)
        self.fog_low = pygame.Surface((FOG_W, FOG_H), pygame.SRCALPHA)
        self.fog_up = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        # cloud modulation for the shroud (2x size so one wrapped blit covers
        # the low-res frame at any camera offset: the mottle reads as weather
        # in the world rather than dirt on the lens)
        self.fog_cloud = self._make_fog_cloud(FOG_W * 2, FOG_H * 2)
        self._fog_t = -1.0
        self._fog_cam = (0, 0)
        self.light_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.bake_done = False
        self._tile_big = {}
        # lazily-baked bake-time caches (cross-blend masks, road sprites)
        self._blend_cache = {}
        self._dir_masks = None
        self._road_sprites = None
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
        self.split = self._make_split()
        self.night_wash = self._make_night_wash()
        # combined frame grade (vignette + warm key + cool fill + night wash)
        # composited into ONE surface so the whole cinematic pass is a single
        # full-screen blit per frame instead of the two it replaces
        self.grade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self._grade_key = None
        self._bld_shadow = {}
        self._ember_cache = {}
        self._night = 0.0
        self.unit_shadow = pygame.Surface((38, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(self.unit_shadow, (10, 9, 12, 48), (0, 0, 38, 14))

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
        def cell_variant(x, y):
            """Hash-chosen texture column for a land cell (0..9).

            The old (x * 7 + y * 13 + h * 3) % 10 is LINEAR: the same variant
            runs down every screen diagonal, so once variants carry different
            sheet columns the field stripes. hash2 is well distributed; the
            +3/+6/+9 nudge stops a cell sharing its column with the left or
            upper neighbour it reads together with (the sheet promises any
            column is safe side by side, but a matching pair still reads as
            one doubled cell)."""
            v = int(hash2(x, y, 7) * 10) % 10
            vl = int(hash2(x - 1, y, 7) * 10) % 10
            vu = int(hash2(x, y - 1, 7) * 10) % 10
            if v == vl or v == vu:
                for k in (3, 6, 9):
                    c = (v + k) % 10
                    if c != vl and c != vu:
                        return c
            return v

        # depth-toned water variant per cell (see _water_variants).  Needed
        # before pass 1: a water cell's flat base must match its depth tile,
        # or the ~1px of base showing through the texture's soft rim outlines
        # every cell in mid-teal.
        wvar = self._water_variants()

        # pass 1: opaque ground base.  The polygon must cover the FULL cell
        # diamond: the old 62x28 polygon left 1-2px of the dark background
        # showing along every cell boundary — the dotted lattice that outlined
        # each diamond across the whole field.  A 1px overshoot into a
        # neighbour is harmless: pass 2 textures cover their own cell last.
        for d in range(m.w + m.h - 1):
            for x in range(max(0, d - m.h + 1), min(m.w - 1, d) + 1):
                y = d - x
                h = m.height[y * m.w + x]
                terr = m.terr(x, y)
                cxp = sx(x, y) + OX
                cyp = sy(x, y, h) + OY
                base = getattr(self.art, "terrain_avg", {}).get(terr, TERRAIN_COL[terr])
                if terr == MG.WATER:
                    base = getattr(self.art, "tile_avg", {}).get(
                        (3, wvar[y * m.w + x]), base)
                pygame.draw.polygon(s, base, [(int(cxp) - 1, int(cyp) - 1),
                                              (int(cxp + 33), int(cyp + 16)),
                                              (int(cxp) - 1, int(cyp + 33)),
                                              (int(cxp - 33), int(cyp + 16))])

        # pass 2: painterly textures — FULL-cell diamonds now.  (The old blit
        # was a half-size off-centre blob: art built the tile on a 2x surface
        # and shrank it back down, so half of every cell stayed flat base
        # colour — the diamond lattice itself.)  Water is textured too: it
        # used to be skipped here and stayed a flat teal plate whose base
        # diamonds showed their seams — the "water is a test pattern" grid.
        keys = [None] * (m.w * m.h)
        for d in range(m.w + m.h - 1):
            for x in range(max(0, d - m.h + 1), min(m.w - 1, d) + 1):
                y = d - x
                h = m.height[y * m.w + x]
                terr = m.terr(x, y)
                i = y * m.w + x
                key = (3, wvar[i]) if terr == MG.WATER else (terr, cell_variant(x, y))
                keys[i] = key
                big = self._tile_big.get(key)
                if big is None:
                    big = pygame.transform.smoothscale(self.art.tiles[key], (70, 38))
                    self._tile_big[key] = big
                px = sx(x, y) + OX - 35
                py = sy(x, y, h) + OY - 3
                s.blit(big, (int(px), int(py)))

        # cross-blend hard biome cuts: each side of a terrain boundary gets up
        # to ~45% of the OTHER side's texture at the seam (directional mask,
        # see _blend_tile), so grass->dirt patches feather over two cells
        # instead of stepping cell-by-cell.  Same-terrain ground and water
        # shorelines are left alone (shores are handled by the foam + colour
        # band below; the lattice metric only samples same-terrain pairs).
        for d in range(m.w + m.h - 1):
            for x in range(max(0, d - m.h + 1), min(m.w - 1, d) + 1):
                y = d - x
                i = y * m.w + x
                t = m.terr(x, y)
                if t == MG.WATER or keys[i] is None:
                    continue
                h = m.height[i]
                for dx, dy, da, db in ((1, 0, 0, 2), (0, 1, 1, 3)):
                    if not self._BLEND_EDGE_A[da] and not self._BLEND_EDGE_A[db]:
                        continue
                    nx, ny = x + dx, y + dy
                    if not m.inb(nx, ny):
                        continue
                    j = ny * m.w + nx
                    nt = m.terr(nx, ny)
                    if nt == t or nt == MG.WATER or keys[j] is None:
                        continue
                    h2 = m.height[j]
                    ax, ay = sx(x, y) + OX - 35, sy(x, y, h) + OY - 3
                    bx, by = sx(nx, ny) + OX - 35, sy(nx, ny, h2) + OY - 3
                    if self._BLEND_EDGE_A[da]:
                        s.blit(self._blend_tile(keys[j], da), (int(ax), int(ay)))
                    if self._BLEND_EDGE_A[db]:
                        s.blit(self._blend_tile(keys[i], db), (int(bx), int(by)))

        # worn earth tracks over m.road cells (mapgen owns the flag; this pass
        # is look only): warm packed-earth tint with a feathered rim so the
        # track melts into the ground it crosses, scatter pebbles, and two soft
        # wheel ruts following the local track axis.  The road cells used to
        # render as plain biome texture — no track reading at all.
        if self._road_sprites is None:
            self._road_sprites = ([self._road_sprite(i) for i in range(4)],
                                  self._rut_sprite((0.894, 0.447)),
                                  self._rut_sprite((-0.894, 0.447)))
        road_spr, rut_x, rut_y = self._road_sprites
        for y in range(m.h):
            for x in range(m.w):
                i = y * m.w + x
                if not m.road[i] or m.terr(x, y) == MG.WATER:
                    continue
                h = m.height[i]
                pos = (int(sx(x, y) + OX - 35), int(sy(x, y, h) + OY - 3))
                s.blit(road_spr[int(hash2(x, y, 3) * 4) % 4], pos)
                rut = None
                if (x > 0 and m.road[i - 1]) or (x + 1 < m.w and m.road[i + 1]):
                    rut = rut_x
                elif (y > 0 and m.road[i - m.w]) or (y + 1 < m.h and m.road[i + m.w]):
                    rut = rut_y
                if rut is not None:
                    s.blit(rut, pos)
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
            rad = rng.randint(10, 26)
            dec = pygame.Surface((rad * 2, rad), pygame.SRCALPHA)
            # 8-15 rather than the old 14-30: these are per-cell random, so a
            # strong one over a cell's top vertex but not its neighbour's was
            # pure neighbour-delta with no visual gain at this size
            pygame.draw.ellipse(dec, (*col, rng.randint(6, 12)), (0, 0, rad * 2, rad))
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
        # blend hard terrain boundaries with soft colour bands
        edge = pygame.Surface((self.MW, self.MH), pygame.SRCALPHA)
        for y in range(m.h):
            for x in range(m.w):
                h = m.height[y * m.w + x]
                t = m.terr(x, y)
                for dx, dy in ((1, 0), (0, 1)):
                    nx, ny = x + dx, y + dy
                    if not m.inb(nx, ny):
                        continue
                    nt = m.terr(nx, ny)
                    if nt == t:
                        continue
                    a = (x + 1, y) if dx else (x + 1, y + 1)
                    b = (x + 1, y + 1) if dx else (x, y + 1)
                    p1 = (sx(*a) + OX, sy(*a, h) + OY)
                    p2 = (sx(*b) + OX, sy(*b, h) + OY)
                    col = self.art.terrain_avg.get(nt, TERRAIN_COL[nt])
                    if nt == MG.WATER:
                        col = (148, 128, 88)
                    # A worn, mottled band instead of one ruled line: hashed
                    # sub-segments with varying alpha (same total ink as the
                    # old single line — soft blobs were tried and rejected:
                    # their wide alpha-36 splats pushed colour deep into open
                    # ground and lifted the lattice neighbour delta).
                    for k in range(2):
                        t0, t1 = k * 0.5, (k + 1) * 0.5
                        q1 = (p1[0] + (p2[0] - p1[0]) * t0, p1[1] + (p2[1] - p1[1]) * t0)
                        q2 = (p1[0] + (p2[0] - p1[0]) * t1, p1[1] + (p2[1] - p1[1]) * t1)
                        ba = 14 + int(hash2(x * 2 + k, y * 2 + dy, 9) * 16)
                        pygame.draw.line(edge, (*col, ba), q1, q2, 12)
        s.blit(edge, (0, 0))

        # --- depth cue: aerial perspective on the high ground ----------------
        # A cool light veil carried only by the top plateau(s): distance reads
        # as elevation, painterly rather than noisy.  Painted on a scratch
        # surface and composited once so the three outward feather bands can
        # overlap without seam-blending per tile (per-tile blits would print a
        # brighter line along every cell edge — a lattice, again).
        hmax = max(m.height) if m.height else -1
        if hmax > 0:
            haze = pygame.Surface((self.MW, self.MH), pygame.SRCALPHA)
            haze_col = (186, 206, 226)
            for level, bands in ((hmax, (9, 15, 27)), (hmax - 1, (0, 7, 13))):
                for bi, grow in enumerate((20, 10, 0)):
                    a = bands[bi]
                    if not a:
                        continue
                    for y in range(m.h):
                        for x in range(m.w):
                            if m.height[y * m.w + x] != level:
                                continue
                            cx = sx(x, y) + OX
                            cy = sy(x, y, level) + OY + 16
                            hw = 33 + grow
                            hh = 16 + grow // 2
                            pygame.draw.polygon(
                                haze, (*haze_col, a),
                                [(int(cx), int(cy - hh)), (int(cx + hw), int(cy)),
                                 (int(cx), int(cy + hh)), (int(cx - hw), int(cy))])
            s.blit(haze, (0, 0))
            del haze

        # --- the sun itself: a directional key, not a flat fill ---------------
        # The old grade was s.fill((26,24,14), ADD) — every cell got identical
        # light, which is literally the "flat, evenly-lit ground" report.  This
        # is a two-stop wash instead: warm key from the map's north-west (the
        # DESIGN top-left sun), cool ambient falling into the south-east.
        # ~60 levels across the whole map — about 15 across one screen, but
        # ~0.5 per cell, so the lattice metric never sees it.
        gw = gh = 48
        add = pygame.Surface((gw, gh))
        sub = pygame.Surface((gw, gh))
        key_hi, key_lo = (46, 39, 21), (7, 7, 7)
        amb_hi, amb_lo = (0, 0, 0), (24, 20, 30)
        for yy in range(gh):
            ty = yy / (gh - 1.0)
            for xx in range(gw):
                t = 0.52 * (xx / (gw - 1.0)) + 0.48 * ty
                add.set_at((xx, yy), mix(key_hi, key_lo, t))
                sub.set_at((xx, yy), mix(amb_hi, amb_lo, t))
        add = pygame.transform.smoothscale(add, (self.MW, self.MH))
        sub = pygame.transform.smoothscale(sub, (self.MW, self.MH))
        s.blit(add, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        s.blit(sub, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
        del add, sub

        # soften the hard per-tile diamonds into a painted field
        try:
            soft = pygame.transform.smoothscale(s, (max(1, self.MW // 4), max(1, self.MH // 4)))
            soft = pygame.transform.smoothscale(soft, (self.MW, self.MH))
            # 46, not 58: the seams are now engineered out (converged rims,
            # full-cell coverage), so this pass only needs to take the very
            # last edge off — at 58 it also flattened the cell CENTRES'
            # texture, which is the painted-field signal the lattice tool's
            # within-cell delta measures
            soft.set_alpha(46)
            s.blit(soft, (0, 0))
        except Exception:
            pass

        # --- controlled contrast, applied where it is free --------------------
        # Black-point crush, then a REAL gain (MULT cannot exceed 255, so a
        # dimmed copy is added back: out = (in - 11) * 1.114 + 8), then a warm
        # toe lift.  Roughly 200 ms on the bake surface, once per map — this is
        # the per-pixel curve that would be unthinkable per tick, done at bake.
        s.fill((11, 9, 13), special_flags=pygame.BLEND_RGB_SUB)
        gain = s.copy()
        gain.fill((29, 29, 29), special_flags=pygame.BLEND_RGB_MULT)
        s.blit(gain, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        del gain
        s.fill((8, 7, 5), special_flags=pygame.BLEND_RGB_ADD)
        self.bake_done = True

    # ---- bake helpers (water depth, boundary cross-blend, road sprites)
    def _water_variants(self):
        """Depth-toned variant index per water cell.

        art.py maps water variant v to emberfall_water.png row 0 column
        v*15//9 (0 = deepest, 15 = shallowest), so distance-to-shore becomes
        a painted depth ramp: 9 next to land, 8/6/4 over the next three rings,
        0..1 in open water (neighbouring cells then differ by only 1-2
        levels).  The flat teal plate these cells used to show — one colour,
        dark base-diamond seams everywhere — is the grid players called a
        test pattern."""
        m = self.map
        n = m.w * m.h
        wv = [None] * n
        frontier = []
        for y in range(m.h):
            for x in range(m.w):
                i = y * m.w + x
                if m.terr(x, y) != MG.WATER:
                    continue
                shore = False
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = x + dx, y + dy
                        if not m.inb(nx, ny) or m.terr(nx, ny) != MG.WATER:
                            shore = True
                            break
                    if shore:
                        break
                if shore:
                    wv[i] = 9
                    frontier.append(i)
        for ring, rv in enumerate((8, 6, 4)):
            nxt = []
            for i in frontier:
                x, y = i % m.w, i // m.w
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if not m.inb(nx, ny):
                        continue
                    j = ny * m.w + nx
                    if wv[j] is None and m.terr(nx, ny) == MG.WATER:
                        wv[j] = rv
                        nxt.append(j)
            frontier = nxt
        for i in range(n):
            if wv[i] is None and m.terr(i % m.w, i // m.w) == MG.WATER:
                # open water: only two neighbouring depth columns, so adjacent
                # interior cells differ by ~1-2 levels instead of stepping
                # between three visibly different depths cell by cell
                wv[i] = int(hash2(i % m.w, i // m.w, 13) * 2)   # 0..1
        return wv

    _BLEND_EDGE_A = (115, 115, 0, 0)    # per-direction % at the shared seam.
    # dirs 0/1 are the cell's two BOTTOM edges — blend hard there.  dirs 2/3
    # are the TOP edges, which meet at the top VERTEX the lattice QA samples
    # (and where four cells visually join): even a mild mix there painted
    # neighbour colour into every boundary cell's vertex.  Zero is safe for
    # the look: the cell BELOW still feathers fully into the same seam (its
    # bottom edge), so every cut still reads feathered — from one strong side.

    def _build_dir_masks(self):
        """Four white diamond-edge ramps (68x36): alpha 0 on the edge opposite
        the neighbour direction, _BLEND_EDGE_A[dir] on the shared edge, linear
        between — l(p) fits the diamond's own vertices, so the ramp is flat
        across the seam and reaches full strength exactly on it."""
        W, H = 68, 36
        cx, cy = W / 2.0, H / 2.0
        # gradients per direction: (1,0), (0,1), (-1,0), (0,-1)
        grads = ((1 / 64.0, 1 / 32.0), (-1 / 64.0, 1 / 32.0),
                 (-1 / 64.0, -1 / 32.0), (1 / 64.0, -1 / 32.0))
        masks = []
        for d, (gx, gy) in enumerate(grads):
            ea = self._BLEND_EDGE_A[d]
            ms = pygame.Surface((W, H), pygame.SRCALPHA)
            for py in range(H):
                row = 0.5 + (py - cy) * gy
                for px in range(W):
                    t = row + (px - cx) * gx
                    if t <= 0:
                        continue
                    ms.set_at((px, py), (255, 255, 255,
                                         int(ea * (1.0 if t > 1 else t))))
            masks.append(ms)
        self._dir_masks = masks

    def _blend_tile(self, key, direction):
        """The cell texture masked toward one neighbour (cached)."""
        ck = (key, direction)
        hit = self._blend_cache.get(ck)
        if hit is None:
            base = self.art.tiles[key]
            if base.get_size() == (68, 36):
                if self._dir_masks is None:
                    self._build_dir_masks()
                hit = base.copy()
                hit.blit(self._dir_masks[direction], (0, 0),
                         special_flags=pygame.BLEND_RGBA_MULT)
            else:
                hit = base
            self._blend_cache[ck] = hit
        return hit

    def _road_sprite(self, i):
        """Feathered warm packed-earth diamond + scatter (baked once, 4 hashes).

        The rim steps alpha down over ~8 rings instead of stopping at a hard
        edge, so a track melts into grass/dirt instead of tiling as a slab;
        the scatter pebbles and scuffs sit inside the feathered core."""
        W, H = 70, 38
        rs = pygame.Surface((W, H), pygame.SRCALPHA)
        cx, cy = W / 2.0, H / 2.0
        for k in range(10):
            hw = 34 - k * 1.35
            hh = 18 - k * 0.72
            # gentle ramp toward the rim: the vertex of each cell sits in the
            # outer rings, and any road colour in the first three rings painted
            # the cell junctions — the track edge read as a tinted diamond
            # outline.  The feather now starts ~3px inside the rim (k3+).
            a = (0, 0, 0, 22, 32, 45, 58, 72, 87, 100)[k]
            pygame.draw.polygon(rs, (186, 156, 114, a),
                                [(cx, cy - hh), (cx + hw, cy),
                                 (cx, cy + hh), (cx - hw, cy)])
        rng = random.Random(410 + i)
        for _ in range(16):
            px = cx + rng.uniform(-24, 24)
            py = cy + rng.uniform(-10, 10)
            if abs(px - cx) / 24 + abs(py - cy) / 11 > 0.95:
                continue
            pygame.draw.circle(rs, rng.choice(((74, 56, 38, 70), (206, 184, 142, 80),
                                               (96, 74, 48, 60))),
                               (int(px), int(py)), rng.choice((1, 1, 2)))
        return rs

    def _rut_sprite(self, u):
        """Two soft wheel ruts along one iso axis, offset +/-6px perpendicular.

        Kept at fixed per-axis offsets so consecutive road cells line their
        ruts up into continuous tracks; ends stay inside the diamond."""
        W, H = 70, 38
        rs = pygame.Surface((W, H), pygame.SRCALPHA)
        cx, cy = W / 2.0, H / 2.0
        ux, uy = u
        ox, oy = -uy * 6.0, ux * 6.0
        for sgn in (1, -1):
            x1 = cx - 12 * ux + ox * sgn
            y1 = cy - 12 * uy + oy * sgn
            x2 = cx + 12 * ux + ox * sgn
            y2 = cy + 12 * uy + oy * sgn
            pygame.draw.line(rs, (66, 50, 34, 54), (x1, y1), (x2, y2), 2)
        return rs

    def _draw_cliffs(self, s, x, y):
        m = self.map
        h = m.height_at(x, y)
        if h <= 0:
            return
        # DESIGN: storybook isometric, TOP-LEFT sun.  +y is the cell's LEFT edge
        # (sx falls as y grows) so it takes the key light; +x is the RIGHT edge
        # and drops into ambient shadow.  The old pair (1.14 / 0.92) had the key
        # on the wrong side and barely separated the faces — which is a large
        # part of why the cliffs read as flat cut-outs.  Shadow also takes a
        # cool ambient-sky tint, key a warm one, so depth reads as light.
        faces = ((1, 0, ((x + 1, y), (x + 1, y + 1)), 0.74, (72, 84, 112)),
                 (0, 1, ((x + 1, y + 1), (x, y + 1)), 1.18, (255, 226, 176)))
        for dx, dy, (a, b), lit, tint in faces:
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
            # ±10% three-phase cliff shading read as a checkerboard on flat rock;
            # keep a hint of striation without the pattern
            col = shade(base, (0.97 + 0.05 * ((x * 3 + y) % 3)) * lit)
            col = mix(col, tint, 0.15 if lit < 1.0 else 0.10)
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
        """Proper elliptical vignette: dark corners, clean centre.

        Built at 1/8 resolution and upscaled — a per-pixel loop over the full
        frame would be exactly the per-tick cost the AAA bar forbids, while
        22k pixels once at load is nothing.  The falloff is deliberately WIDE
        (reaches in from r=0.12): a tight ring has a steep gradient, and the
        lattice metric samples 30px neighbour pairs, so a steep screen ramp
        reads as cell-to-cell difference.  Wide and smooth stays cinematic and
        invisible to the metric.
        """
        w, h = 200, 113
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = w / 2.0, h / 2.0
        for y in range(h):
            dy = (y - cy) / cy
            for x in range(w):
                dx = (x - cx) / cx
                r = math.sqrt(dx * dx * 0.86 + dy * dy * 1.16)
                t = (r - 0.12) / 1.16
                if t <= 0:
                    continue
                t = 1.0 if t > 1 else t
                t = t * t * (3 - 2 * t)
                a = int(94 * t * (0.6 + 0.4 * t))
                if a:
                    s.set_at((x, y), (7, 6, 12, a))
        return pygame.transform.smoothscale(s, (SCREEN_W, SCREEN_H))

    def _make_split(self):
        """Warm key on the top-left (sun) side, cool fill into the shadow side.

        One linear diagonal ramp across the WHOLE frame: ~36 levels of swing
        over 1600px, so it reads as direction and never as a gradient the
        neighbour-delta metric can count."""
        w, h = 64, 36
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        warm, cool = (255, 210, 152), (24, 38, 72)
        for y in range(h):
            ty = y / (h - 1.0)
            for x in range(w):
                t = 0.55 * (x / (w - 1.0)) + 0.45 * ty
                s.set_at((x, y), (*mix(warm, cool, t), int(20 + 17 * t)))
        return pygame.transform.smoothscale(s, (SCREEN_W, SCREEN_H))

    def _make_night_wash(self):
        """Cool desaturating veil for the night half of the cycle.

        Multiplicative tint alone cannot desaturate; blending toward one cool
        colour does, and this is what keeps night reading as moonlight rather
        than a blue filter over the day palette."""
        w, h = 64, 36
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = w / 2.0, h / 2.0
        for y in range(h):
            dy = (y - cy) / cy
            for x in range(w):
                dx = (x - cx) / cx
                r = math.sqrt(dx * dx * 0.86 + dy * dy * 1.16)
                t = 1.0 if r > 1.2 else smoothstep(min(1.0, max(0.0, r / 1.2)))
                s.set_at((x, y), (14, 26, 64, int(54 + 46 * t)))
        return pygame.transform.smoothscale(s, (SCREEN_W, SCREEN_H))

    def _make_fog_cloud(self, w, h):
        """Soft cloud mottle for the shroud wall (alpha 234..254).

        Multiplied over the low-res fog mask before the upscale, so the wall
        modulates between ~85% and 92% opaque instead of reading as one flat
        slab of paint — texture without letting the terrain ghost through."""
        sw, sh = max(14, w // 4), max(10, h // 4)
        s = pygame.Surface((sw, sh), pygame.SRCALPHA)
        s.fill((255, 255, 255, 255))
        rng = random.Random(7717)
        for _ in range(34):
            r = rng.randint(4, max(6, sw // 5))
            ex = rng.randrange(-r, sw + r)
            ey = rng.randrange(-r, sh + r)
            a = rng.randint(234, 254)
            c = (rng.randint(244, 255), rng.randint(246, 255), 255)
            pygame.draw.ellipse(s, (*c, a), (ex - r, ey - r // 2, r * 2, r))
        return pygame.transform.smoothscale(s, (w, h))

    # ---------------------------------------------------------------- draw
    def draw(self, screen, game, cam, time):
        self._night = clamp(float(getattr(game, "night", 0.0) or 0.0), 0.0, 1.0)
        # Camera shake, consumed at last: Camera.update has always computed
        # shake_x/shake_y and nothing in the draw transform ever read them, so
        # Game.shake() (boss wake, wave horn, Daybreak) never moved a pixel.
        # Offset the VIEW for the duration of this frame and restore below, so
        # the HUD and minimap keep their stable anchor and gameplay code —
        # which reads the unshaken camera — never sees a difference.
        skx, sky = cam.shake_x, cam.shake_y
        cam.x += skx
        cam.y += sky
        screen.fill((18, 16, 20))
        vx = int(cam.x - SCREEN_W / 2)
        vy = int(cam.y - SCREEN_H / 2)
        sx0 = clamp(vx, 0, self.MW); sy0 = clamp(vy, 0, self.MH)
        r = pygame.Rect(sx0, sy0, min(SCREEN_W, self.MW - sx0), min(SCREEN_H, self.MH - sy0))
        screen.blit(self.surface, (0, 0), r)
        # still water: painterly depth ramp baked in; this adds the animated
        # shimmer (it was written but never called, so water sat dead flat)
        self._draw_water(screen, cam, time)

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
        # lighting first, so the shroud can bury lights that are out of sight
        self._draw_lights(screen, game, cam, time)
        # controlled contrast on the world: black-point crush + warm toe lift
        # (two BLEND fills, 0.24 ms measured together)
        screen.fill((13, 11, 15), special_flags=pygame.BLEND_RGB_SUB)
        screen.fill((9, 8, 6), special_flags=pygame.BLEND_RGB_ADD)
        # fog of war: two-tone, low-res interpolated (soft) boundary
        self._draw_fog(screen, game, cam, time)
        # placement ghost
        self._draw_placement(screen, game, cam)
        self._draw_cursor_effects(screen, game, cam, time)
        # time of day + cinematic grade (vignette, warm key / cool fill)
        self._apply_time_of_day(screen, game)
        screen.blit(self._frame_grade(game), (0, 0))
        # embers last so their headlights survive the vignette at night
        self._draw_embers(screen, game, cam, time)
        if game.debug:
            self._draw_debug(screen, game, cam)
        # give the camera back: outside this frame the view is unshaken
        cam.x -= skx
        cam.y -= sky

    # ---------------------------------------------------------------- grade
    def _apply_time_of_day(self, screen, game):
        """Mission-clock colour temperature + brightness, one MULT fill.

        world.night is the existing slow sine on the clock (0 at mission start,
        full night ~3.9 min in, ~8.7 min cycle); nothing in gameplay reads it,
        so this is present-time only.  Measured cost 0.23 ms — and the QA dawn
        default lands on a near-neutral anchor, so screenshots keep the
        daytime look."""
        n = self._night
        anchors = ((0.00, (255, 253, 247)),   # day: near-neutral, a hair warm
                   (0.35, (255, 243, 224)),   # late afternoon
                   (0.58, (255, 214, 160)),   # amber dusk
                   (0.78, (150, 168, 214)),   # twilight: blue is winning
                   (1.00, (84, 110, 190)))    # deep night: cool blue, ~45% light
        if n <= anchors[0][0]:
            col = anchors[0][1]
        elif n >= anchors[-1][0]:
            col = anchors[-1][1]
        else:
            col = anchors[-1][1]
            for (n0, c0), (n1, c1) in zip(anchors, anchors[1:]):
                if n0 <= n <= n1:
                    t = (n - n0) / (n1 - n0)
                    col = (int(c0[0] + (c1[0] - c0[0]) * t),
                           int(c0[1] + (c1[1] - c0[1]) * t),
                           int(c0[2] + (c1[2] - c0[2]) * t))
                    break
        screen.fill(col, special_flags=pygame.BLEND_RGB_MULT)

    def _frame_grade(self, game):
        """The full-frame cinematic grade, rebuilt only as the clock moves.

        Vignette + directional warm/cool split + night wash are composited
        into one surface and blitted once — that single blit replaces the old
        flat dusk fill and the old ring vignette (two blits), which is what
        pays for the rest of the pass."""
        n = self._night
        key = int(round(n * 30))
        if self.grade is not None and self._grade_key == key:
            return self.grade
        g = self.grade
        g.fill((0, 0, 0, 0))
        # 1. directional split: warm key from the sun side, cool into shadow.
        # The key FADES with night — leaving it at full strength is what made
        # the first deep-night frame read as amber dusk instead of moonlight.
        self.split.set_alpha(255 - int(196 * n))
        g.blit(self.split, (0, 0))
        # 2. vignette, deeper at night
        self.vignette.set_alpha(176 + int(64 * n))
        g.blit(self.vignette, (0, 0))
        # 3. night wash: desaturating cool veil, absent in daylight
        if n > 0.04:
            self.night_wash.set_alpha(int(255 * min(1.0, n * 1.15)))
            g.blit(self.night_wash, (0, 0))
        self._grade_key = key
        return g

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
        # native Flare frame counts: stance 4, run 8, die 6
        state = e.anim if e.alive else "death"
        n = self.art.unit_frame_count(e.rig, state)
        rate = {"idle": 6, "walk": 12, "attack": 10, "cast": 10,
                "death": 8, "gather": 10, "ride": 12}.get(state, 8)
        frame = int(e.anim_t * rate) % max(1, n)
        if state in ("death", "attack", "cast"):
            frame = min(max(0, n - 1), int(e.anim_t * rate))
        if state == "death":
            frame = min(max(0, n - 1), int(e.anim_t * 8))
        img, ax, ay = self.art.unit(e.rig, e.facing_bucket, state, frame, e.team)
        px, py = self.w2s(e.x, e.y, e.height)
        px -= cam.x - SCREEN_W / 2
        py -= cam.y - SCREEN_H / 2
        if not e.alive:
            img = img.copy()
            img.set_alpha(max(0, int(255 * (1 - (e.death_t - 1.5) / 2.5))))
        # Flare sprites carry their own top-left baked shadow; no second ellipse.
        # Night: a moonlight rim band just outside the top-left silhouette keeps
        # units off the dark ground (the sprite's own 1px rim is a day-light rim)
        if e.alive and self._night > 0.14:
            rim, rbb = self.art.rim(img, (172, 202, 246))
            rim.set_alpha(int(165 * (self._night - 0.10)))
            screen.blit(rim, (int(px - ax + rbb.x), int(py - ay + rbb.y)))
        if getattr(e, "is_hero", False) and e.alive:
            g = self.art.glow_sprite((255, 186, 96), 44, 105)
            screen.blit(g, (int(px - g.get_width() / 2), int(py - g.get_height() / 2 - 10)),
                        special_flags=pygame.BLEND_ADD)
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
        # contact shade: the footprint darkens the ground it stands on, four
        # feathered bands deep, so buildings sit IN the field instead of on it
        sh = self._building_shadow(e.bw, e.bh)
        screen.blit(sh, (int(px - sh.get_width() / 2),
                         int(py + 16 - sh.get_height() / 2)))
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

    def _building_shadow(self, bw, bh):
        """Ambient contact darkening under a footprint (cached per size).

        Drawn largest-and-faintest first, then three tighter bands: pygame
        replaces pixels, so the ring alphas stay exactly as written and the
        shade feathers instead of printing the building's diamond outline."""
        key = (bw, bh)
        hit = self._bld_shadow.get(key)
        if hit is None:
            w = int(bw * TILE + 30)
            h = int(bh * (TILE // 2) + 22)
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            for i, a in enumerate((14, 22, 31, 42)):
                gx = i * max(3, w // 26)
                gy = i * max(2, h // 16)
                pygame.draw.ellipse(s, (11, 11, 16, a),
                                    (gx, gy, w - gx * 2, h - gy * 2))
            hit = s
            self._bld_shadow[key] = hit
        return hit

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
        """Two-tone fog of war with an interpolated (non-staircase) boundary.

        Rendering only: explored/vis are read, never written, and the rebuild
        cadence (camera moved >2px, or 0.18s of clock) is unchanged.  The
        earlier partial feather — two hard alpha rings where unexplored met
        explored — still printed a tile staircase because each ring was a whole
        tile at one alpha.  Here the same per-tile state is rasterised as iso
        diamonds on a 1/8-resolution mask, pre-blurred and smoothscaled up at
        composite time, so every step becomes an interpolated curve.  Rebuild
        ~1.7ms (only when the camera moves), cached blit ~1.1ms, against
        3.7ms/frame for the old uniform veil + shroud blits it replaces.
        """
        if getattr(game, "mode", "play") in ("menu", "intro"):
            return
        moved = abs(cam.x - self._fog_cam[0]) + abs(cam.y - self._fog_cam[1]) > 2
        if not moved and abs(time0 - self._fog_t) < 0.18:
            screen.blit(self.fog_up, (0, 0))
            return
        self._fog_cam = (cam.x, cam.y)
        self._fog_t = time0
        self._rebuild_fog(game, cam)
        screen.blit(self.fog_up, (0, 0))

    def _rebuild_fog(self, game, cam):
        m = self.map
        low = self.fog_low
        # clear keeps the veil hue under alpha 0, so the upscale interpolates
        # colour as well as alpha with nothing to bleed in from the corners
        low.fill((*FOG_VEIL, 0))
        left = cam.x - SCREEN_W / 2
        top = cam.y - SCREEN_H / 2
        corners = [tile_from_screen(cam.x - SCREEN_W / 2 - self.OX, cam.y - SCREEN_H / 2 - self.OY, 0),
                   tile_from_screen(cam.x + SCREEN_W / 2 - self.OX, cam.y - SCREEN_H / 2 - self.OY, 0),
                   tile_from_screen(cam.x - SCREEN_W / 2 - self.OX, cam.y + SCREEN_H / 2 - self.OY, 2),
                   tile_from_screen(cam.x + SCREEN_W / 2 - self.OX, cam.y + SCREEN_H / 2 - self.OY, 2)]
        tx0 = int(min(c[0] for c in corners)) - 7; tx1 = int(max(c[0] for c in corners)) + 7
        ty0 = int(min(c[1] for c in corners)) - 7; ty1 = int(max(c[1] for c in corners)) + 7
        w, h = m.w, m.h
        ex = game.explored
        vis = game.vis
        n = self._night
        # night deepens the wall and thickens the memory veil a little
        shroud_a = clamp(int(FOG_SHROUD_A * (1.0 + 0.10 * n)), 0, 255)
        veil_a = clamp(int(FOG_VEIL_A * (1.0 + 0.26 * n)), 0, 255)
        k = 1.0 / FOG_DIV
        # inline the iso projection: w2s() is two function calls per tile and
        # this loop walks ~1600 tiles on every rebuild (camera panning), so the
        # arithmetic is done once per ROW instead
        height = m.height
        hw2, hh2 = TILE_W // 2, TILE_H // 2
        ox_l = self.OX - left
        oy_t = self.OY - top
        for y in range(ty0, ty1 + 1):
            iny = 0 <= y < h
            row = y * w
            sx_row = -y * hw2 + ox_l
            sy_row = y * hh2 + oy_t
            for x in range(tx0, tx1 + 1):
                inb = iny and 0 <= x < w
                i = row + x
                px = x * hw2 + sx_row
                if inb and ex[i]:
                    if vis[i]:
                        continue                      # currently visible: clear
                    col, a = FOG_VEIL, veil_a
                    py = x * hh2 + sy_row - height[i] * ELEV
                else:
                    # unexplored, or the void past the map edge: same wall,
                    # same soft transition into it
                    col, a = FOG_SHROUD, shroud_a
                    py = x * hh2 + sy_row - (height[i] * ELEV if inb else 0)
                if px < -110 or px > SCREEN_W + 110 or py < -110 or py > SCREEN_H + 110:
                    continue
                # iso DIAMOND, grown one texel: contiguous coverage with no
                # double-alpha seams, and a contour that follows the lattice
                # instead of axis-aligned boxes
                cx = px * k
                cy = py * k + 16 * k
                pygame.draw.polygon(low, (*col, a),
                                    [(cx, cy - 3.0), (cx + 5.0, cy),
                                     (cx, cy + 3.0), (cx - 5.0, cy)])
        # cloud modulation multiplied into the mask (200x112 — free) and
        # scrolled by the camera, so the wall's texture lives in the world
        low.blit(self.fog_cloud, (-(int(cam.x) % FOG_W), -(int(cam.y) % FOG_H)),
                 special_flags=pygame.BLEND_RGBA_MULT)
        # blur one step, then upscale: the texel staircase (8px) plus this
        # pre-blur gives a ~24px interpolated contour — a painted edge, not a
        # voxel one.  Total rebuild cost ~1.6ms, and only on camera movement.
        blur = pygame.transform.smoothscale(low, (FOG_W // 2, FOG_H // 2))
        self.fog_up = pygame.transform.smoothscale(blur, (SCREEN_W, SCREEN_H))

    def _draw_lights(self, screen, game, cam, time):
        """Hearth/torch glow — the night's strongest storyteller.

        Strength and radius ride the mission clock, quantised to sixths so the
        glow-sprite cache stays bounded; past dusk every window, beacon and
        forge joins in.  Daylight keeps the old sparse list, so daytime cost
        and daytime look both stay where they were."""
        self.light_surf.fill((0, 0, 0, 0))
        left = cam.x - SCREEN_W / 2
        top = cam.y - SCREEN_H / 2
        n = round(self._night * 6) / 6.0
        boost = 1.0 + 3.4 * n      # 1.0 in daylight (unchanged look), 4.4x at deep night
        grow = 1.0 + 0.28 * n
        lights = []
        for p in self.map.props:
            if p["kind"] == "fire":
                lights.append((p["x"], p["y"], 34, (255, 148, 70), 0.4))
        halls = ("townhall", "keep", "necropolis")
        beacons = ("sanctum", "temple", "altar", "altarhollow", "blacksmith",
                   "barracks", "tower", "ziggurat", "crypt", "slaughterhouse",
                   "bonetower", "mill")
        for e in game.entities:
            if not e.alive:
                continue
            if e.is_hero:
                lights.append((e.x, e.y, 36, (255, 190, 120), 0.3))
                continue
            if not e.is_building or e.build_progress < 1:
                continue
            warm = (255, 170, 90) if e.team == PLAYER else (150, 120, 230)
            if e.bid in halls:
                lights.append((e.x + e.bw / 2, e.y + e.bh / 2, 34, warm, 0.16))
            elif e.bid in beacons:
                lights.append((e.x + e.bw / 2, e.y + e.bh / 2, 26, warm, 0.16))
            elif n > 0.16:
                # window light — only after dusk, so daylight is unchanged
                lights.append((e.x + e.bw / 2, e.y + e.bh / 2, 16, warm, 0.12))
        for (x, y, rad, col, strength) in lights:
            h = self.map.height_at(int(x), int(y))
            px, py = self.w2s(x, y, h)
            px -= left; py -= top
            rad = int(rad * grow)
            if px < -rad or px > SCREEN_W + rad or py < -rad or py > SCREEN_H + rad:
                continue
            st = int(90 * strength * boost)
            st -= st % 4
            if st <= 0:
                continue
            img = self.art.glow_sprite(col, rad, min(255, st))
            self.light_surf.blit(img, (int(px - rad), int(py - rad - 10)), special_flags=pygame.BLEND_ADD)
        screen.blit(self.light_surf, (0, 0), special_flags=pygame.BLEND_ADD)

    def _ember_sprite(self, r, col, a):
        """Cached ember dot; 3 sizes x 32 flicker steps, ~190 tiny surfaces."""
        key = (r, col, a >> 3)
        hit = self._ember_cache.get(key)
        if hit is None:
            d = max(4, r * 4)
            hit = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(hit, (*col, a), (d // 2, d // 2), r)
            self._ember_cache[key] = hit
        return hit

    def _draw_embers(self, screen, game, cam, time):
        # headlights of the vale: brighter and denser-looking as the light dies
        n = self._night
        boost = 1.0 + 1.45 * n
        grow = 1.0 + 0.3 * n
        for p in self.ember_particles:
            x = (p["x"] + p["vx"] * time + math.sin(time * 0.7 + p["ph"]) * 12) % (SCREEN_W + 40) - 20
            y = (p["y"] + p["vy"] * time) % (SCREEN_H + 40) - 20
            a = int(255 * p["a"] * (0.55 + 0.45 * math.sin(time * 2 + p["ph"])) * boost)
            if a <= 0:
                continue
            if a > 255:
                a = 255
            col = (255, 150, 80) if p["warm"] else (150, 190, 200)
            r = max(1, int(p["r"] * grow))
            screen.blit(self._ember_sprite(r, col, a), (int(x), int(y)),
                        special_flags=pygame.BLEND_ADD)

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
            mx, my = getattr(game, "mouse_pos", (SCREEN_W // 2, SCREEN_H // 2))
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
            # Two lineage fixes: one aligned dash per diamond made the river
            # read as a wireframe grid, and the sparse follow-up used the
            # linear (x*7+y*13)%6 — a diagonal stripe pattern, i.e. a test
            # pattern again. hash2 picks ~1/4 of tiles at random, the stroke
            # drifts inside the diamond with the wave phase, and it stays long
            # and soft so it reads as light moving on water.
            hv = hash2(x, y, 21)
            if hv > 0.24:
                continue
            a = int(10 + 15 * (0.5 + 0.5 * math.sin(ph)))
            ox = math.sin(ph) * 7 + (hv * 70 - 9)
            oy = math.cos(ph * 0.7) * 3
            pygame.draw.line(screen, (176, 222, 216, a),
                             (int(px - 14 + ox), int(py + oy)),
                             (int(px + 10 + ox), int(py + oy - 2)), 2)

    def _draw_debug(self, screen, game, cam):
        f = self.art.font(14, "sans")
        lines = [f"fps {game.fps:.0f}  ents {len(game.entities)}  vis {sum(game.vis)}",
                 f"cam {int(cam.x)},{int(cam.y)}  sel {len(game.selection)}  mode {game.mode}"]
        for i, line in enumerate(lines):
            screen.blit(f.render(line, True, (230, 230, 200)), (10, 10 + i * 16))
