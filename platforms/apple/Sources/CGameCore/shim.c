/*
 * shim.c -- no implementation lives here.
 *
 * Every gc_* symbol is provided at link time by libgame_core.dylib (built from
 * core/ with `cargo build --release`).  This translation unit exists for two
 * reasons:
 *
 *   1. SwiftPM only accepts a C target that actually contains a source file;
 *      the module map alone is not enough.
 *   2. It turns the ABI assumptions made by the Swift wrapper into *compile
 *      time* checks.  If anybody edits include/game_core.h and changes a struct,
 *      the macOS/iOS build fails right here instead of silently mis-reading the
 *      command buffer at runtime.
 *
 * Byte sizes expected by Sources/SlimeArenaRenderer/GameCore.swift:
 *
 *   gc_cmd      56 bytes   (14 x 4-byte fields, alignment 4)
 *   gc_input    28 bytes   (7  x 4-byte fields, alignment 4)
 *   gc_event    16 bytes   (4  x 4-byte fields, alignment 4)
 *   gc_status   40 bytes   (10 x 4-byte fields, alignment 4)
 */
#include "game_core.h"

_Static_assert(sizeof(gc_cmd) == 56,
               "gc_cmd layout changed: update GameCore.swift and MetalRenderer.swift");
_Static_assert(sizeof(gc_input) == 28,
               "gc_input layout changed: update GameCore.swift / Input.swift");
_Static_assert(sizeof(gc_event) == 16,
               "gc_event layout changed: update GameCore.swift / AudioHaptics.swift");
_Static_assert(sizeof(gc_status) == 40,
               "gc_status layout changed: update GameCore.swift");

/* Offsets the renderer depends on; also checked field by field in Swift. */
_Static_assert(offsetof(gc_cmd, kind) == 0, "gc_cmd.kind moved");
_Static_assert(offsetof(gc_cmd, sprite) == 4, "gc_cmd.sprite moved");
_Static_assert(offsetof(gc_cmd, x) == 8, "gc_cmd.x moved");
_Static_assert(offsetof(gc_cmd, y) == 12, "gc_cmd.y moved");
_Static_assert(offsetof(gc_cmd, w) == 16, "gc_cmd.w moved");
_Static_assert(offsetof(gc_cmd, h) == 20, "gc_cmd.h moved");
_Static_assert(offsetof(gc_cmd, rot) == 24, "gc_cmd.rot moved");
_Static_assert(offsetof(gc_cmd, rgba) == 28, "gc_cmd.rgba moved");
_Static_assert(offsetof(gc_cmd, u0) == 32, "gc_cmd.u0 moved");
_Static_assert(offsetof(gc_cmd, v0) == 36, "gc_cmd.v0 moved");
_Static_assert(offsetof(gc_cmd, u1) == 40, "gc_cmd.u1 moved");
_Static_assert(offsetof(gc_cmd, v1) == 44, "gc_cmd.v1 moved");
_Static_assert(offsetof(gc_cmd, flags) == 48, "gc_cmd.flags moved");
_Static_assert(offsetof(gc_cmd, _pad) == 52, "gc_cmd._pad moved");
_Static_assert(offsetof(gc_input, buttons) == 24, "gc_input.buttons moved");
_Static_assert(offsetof(gc_status, player_hp) == 28, "gc_status.player_hp moved");

/* The ABI version this renderer was written against.  build_macos.sh greps both
 * this line and GameCore.swift and fails the build if they disagree. */
_Static_assert(GC_ABI_VERSION == 1u, "GC_ABI_VERSION changed: review the Swift wrapper");
