"""Audio bus: music, ambience and SFX with graceful fallbacks."""
from __future__ import annotations
import os
import pygame

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AUDIO = os.path.join(ROOT, "assets", "audio")
ALIAS = {"build_done": "build-done", "level": "level-up", "build_done": "build-done"}


class Audio:
    def __init__(self, enabled=True):
        self.enabled = enabled and os.environ.get("EMBERFALL_NO_AUDIO") != "1"
        self.ok = False
        self.sfx = {}
        self.music = {}
        self.music_vol = 0.5
        self.sfx_vol = 0.72
        self._current = None
        self._played = {}
        if not self.enabled:
            return
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(32)
            self.ok = True
        except Exception:
            self.ok = False
            return
        d = os.path.join(AUDIO, "sfx")
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.endswith((".ogg", ".wav")):
                    try:
                        self.sfx[fn.rsplit(".", 1)[0]] = pygame.mixer.Sound(os.path.join(d, fn))
                    except Exception:
                        pass
        md = os.path.join(AUDIO, "music")
        if os.path.isdir(md):
            for fn in os.listdir(md):
                if fn.endswith((".ogg", ".wav")):
                    self.music[fn.rsplit(".", 1)[0]] = os.path.join(md, fn)
        for s in self.sfx.values():
            s.set_volume(self.sfx_vol)

    def play(self, name, volume=1.0):
        if not self.ok:
            return
        key = ALIAS.get(name, name)
        s = self.sfx.get(key)
        if not s:
            return
        ch = pygame.mixer.find_channel(True)
        if ch:
            ch.set_volume(self.sfx_vol * volume)
            ch.play(s)

    def play_music(self, name, fade=900):
        if not self.ok:
            return
        if self._current == name:
            return
        path = self.music.get(name)
        if not path:
            return
        try:
            pygame.mixer.music.fadeout(fade)
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.music_vol)
            pygame.mixer.music.play(-1, fade_ms=fade)
            self._current = name
        except Exception:
            pass

    def stop_music(self):
        if self.ok:
            try:
                pygame.mixer.music.fadeout(500)
            except Exception:
                pass
        self._current = None

    def set_music(self, v):
        self.music_vol = max(0.0, min(1.0, v))
        if self.ok:
            pygame.mixer.music.set_volume(self.music_vol)

    def set_sfx(self, v):
        self.sfx_vol = max(0.0, min(1.0, v))
        for s in self.sfx.values():
            s.set_volume(self.sfx_vol)
