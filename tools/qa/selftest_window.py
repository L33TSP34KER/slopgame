#!/usr/bin/env python3
"""Harness self-test: a minimal pygame window that animates, so run_qa.py can be
validated end-to-end before the real game exists.

    python3 tools/qa/run_qa.py --cmd ".venv/bin/python tools/qa/selftest_window.py"
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import pygame
except ImportError:
    sys.stderr.write("pygame not importable\n")
    raise

pygame.init()
screen = pygame.display.set_mode((1600, 900))
pygame.display.set_caption("emberfall qa selftest")
clock = pygame.time.Clock()
frame = 0
t0 = time.time()
running = True
while running and time.time() - t0 < 40:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
    screen.fill((30, 46, 34))
    x = int((frame * 7) % 1600)
    pygame.draw.rect(screen, (217, 164, 65), (x, 400, 120, 80))
    pygame.draw.circle(screen, (168, 58, 58), (800, 700), 60)
    pygame.display.flip()
    frame += 1
    clock.tick(60)
    if frame % 60 == 0:
        print(json.dumps({"qa": {"frame": frame, "fps": round(clock.get_fps(), 1),
                                 "elapsed": round(time.time() - t0, 1)}}), flush=True)
pygame.quit()
