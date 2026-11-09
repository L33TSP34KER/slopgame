#!/usr/bin/env python3
"""Independent scene renderer for art QA (mimo, tools/qa/).

Runs deepseek's `tools/scene_test.py` UNMODIFIED, with two safe shims:

1. `Art._make_prop` is wrapped so a broken prop branch (the live
   `stone` UnboundLocalError in art.py) yields a visible placeholder instead
   of killing the whole render — the crash is still reported in the output.
2. `pygame.image.save` is redirected into `design/notes/shots/` so this pass
   never overwrites the engine author's own test renders.

    python3 tools/qa/scene_shots.py                 # -> design/notes/shots/scene-*.png
    python3 tools/qa/scene_shots.py --with-crash    # reproduce the raw crash
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "emberfall"))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

OUT = os.path.join(ROOT, "design", "notes", "shots")
pygame.init()
pygame.display.set_mode((1600, 900))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-crash", action="store_true",
                    help="run without the prop shim to reproduce engine crashes")
    args = ap.parse_args()

    from src import art as art_mod

    failures: list[str] = []

    if not args.with_crash:
        orig = art_mod.Art._make_prop

        def safe_make_prop(self, kind, variant, frame):  # noqa: ANN001
            try:
                return orig(self, kind, variant, frame)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{type(exc).__name__}: {exc} (kind={kind!r})")
                surf = pygame.Surface((44, 44), pygame.SRCALPHA)
                pygame.draw.circle(surf, (220, 70, 70), (22, 22), 14, 3)
                pygame.draw.line(surf, (220, 70, 70), (8, 8), (36, 36), 3)
                return surf, 22.0, 40.0

        art_mod.Art._make_prop = safe_make_prop  # type: ignore[method-assign]

    os.makedirs(OUT, exist_ok=True)

    real_save = pygame.image.save

    def redirect_save(surface, name, *a, **kw):  # noqa: ANN001
        base = os.path.basename(str(name))
        target = os.path.join(OUT, f"scene-{base}")
        return real_save(surface, target, *a, **kw)

    pygame.image.save = redirect_save  # type: ignore[assignment]

    script = os.path.join(ROOT, "tools", "scene_test.py")
    code = compile(open(script, encoding="utf-8").read(), script, "exec")
    glb = {"__name__": "__main__", "__file__": script}
    try:
        exec(code, glb)  # noqa: S102 — runs the engine's own test scene
    except Exception as exc:  # noqa: BLE001
        failures.append(f"scene_test crashed: {type(exc).__name__}: {exc}")

    print(f'{{"qa": {{"scene_shots": "done", "prop_failures": {len(failures)}}}}}')
    for f in dict.fromkeys(failures):
        print(" -", f)
    print(f"shots in {OUT}")
    return 1 if any("scene_test crashed" in f for f in failures) else 0


if __name__ == "__main__":
    sys.exit(main())
