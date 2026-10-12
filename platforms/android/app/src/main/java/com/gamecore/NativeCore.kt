package com.gamecore

/**
 * The only Kotlin door into `libgame_core.so`.
 *
 * ## What Kotlin is allowed to see
 *
 * A single opaque handle as a [Long].  There is no pointer arithmetic, no
 * `ByteBuffer` aliasing and no way to build a valid handle by hand; the value is
 * only ever handed straight back to the native side.
 *
 * ## Instance vs. static native methods (deliberate!)
 *
 * These are declared as **instance** members of a Kotlin `object`, so the JVM
 * emits `Java_com_gamecore_NativeCore_nativeX` with a `jobject` receiver, which
 * is exactly the shape `game_jni.c` implements.  `@JvmStatic` is intentionally
 * *not* used: on an `object` it also emits a static bridge with the same name
 * and descriptor, which makes JNI auto-binding ambiguous.  Do not add it.
 *
 * ## Thread affinity
 *
 * `gc_create` binds the core to the calling thread, and every entry point is
 * thread-affine to it.  [nativeCreate] is therefore called on the GL thread
 * (inside `GameRenderer.onSurfaceCreated`) and every other call in this file is
 * made from the GL thread only.  Nothing here is thread safe.
 *
 * ## Array packing (mirrors the constants at the bottom of game_jni.c)
 *
 * [nativeFillCommands] writes SoA with a fixed stride -- see [FLOATS_PER_CMD]
 * and [INTS_PER_CMD].  The arrays are owned and reused by `GameRenderer`; they
 * are never reallocated in the steady state.
 */
object NativeCore {

    /**
     * Non-null when the native library could not be loaded at all.
     *
     * `libgame_jni.so` has `libgame_core.so` as a `DT_NEEDED` entry, so loading
     * the shim also brings the Rust core in; there is deliberately no second
     * `loadLibrary` call.  Declared first so the object can finish initialising
     * even when the load fails, which lets the UI report it instead of dying with
     * `ExceptionInInitializerError`.
     */
    val loadFailure: UnsatisfiedLinkError? = try {
        System.loadLibrary("game_jni")
        null
    } catch (e: UnsatisfiedLinkError) {
        e
    }

    /** Must equal `GC_ABI_VERSION` in include/game_core.h. */
    const val EXPECTED_ABI_VERSION: Int = 1

    // ---- packing strides: keep in sync with game_jni.c -------------------

    /** floats per `gc_cmd`: x, y, w, h, rot, u0, v0, u1, v1. */
    const val FLOATS_PER_CMD: Int = 9

    /** ints per `gc_cmd`: kind, sprite, rgba (0xAARRGGBB bits), flags. */
    const val INTS_PER_CMD: Int = 4

    /** floats per `gc_event`: x, y, value. */
    const val FLOATS_PER_EVENT: Int = 3

    /** ints per `gc_event`: type. */
    const val INTS_PER_EVENT: Int = 1

    /** ints in a `gc_status`: wave, level, kills, money, score, best, state. */
    const val STATUS_INTS: Int = 7

    /** floats in a `gc_status`: player_hp, player_hp_max, time_alive. */
    const val STATUS_FLOATS: Int = 3

    // ---- gc_cmd_kind (include/game_core.h) -------------------------------
    const val CMD_SPRITE: Int = 1
    const val CMD_RECT: Int = 2
    const val CMD_GLYPH: Int = 3

    // ---- GC_FLAG_* (include/game_core.h) ---------------------------------
    const val FLAG_NONE: Int = 0
    const val FLAG_FLASH: Int = 1 // additive blend
    const val FLAG_SHADOW: Int = 2 // soft dark offset copy, emitted by the CPU

    // ---- gc_event_type (include/game_core.h) -----------------------------
    const val EVT_SHOOT: Int = 1
    const val EVT_HIT: Int = 2
    const val EVT_ENEMY_DIE: Int = 3
    const val EVT_PLAYER_HURT: Int = 4
    const val EVT_PICKUP_XP: Int = 5
    const val EVT_PICKUP_MONEY: Int = 6
    const val EVT_LEVEL_UP: Int = 7
    const val EVT_BUY: Int = 8
    const val EVT_BUY_FAIL: Int = 9
    const val EVT_WAVE_START: Int = 10
    const val EVT_WAVE_CLEAR: Int = 11
    const val EVT_GAME_OVER: Int = 12
    const val EVT_UI_CLICK: Int = 13
    const val EVT_DASH: Int = 14

    // ---- gc_game_state ---------------------------------------------------
    const val STATE_TITLE: Int = 0
    const val STATE_PLAYING: Int = 1
    const val STATE_LEVEL_UP: Int = 2
    const val STATE_SHOP: Int = 3
    const val STATE_PAUSED: Int = 4
    const val STATE_GAME_OVER: Int = 5

    // ---- GC_BTN_* --------------------------------------------------------
    const val BTN_DASH: Int = 1 shl 0
    const val BTN_PAUSE: Int = 1 shl 1
    const val BTN_RESTART: Int = 1 shl 2

    // ---- library version -------------------------------------------------

    /** `gc_abi_version()`.  Callable before anything else; loads the library. */
    external fun nativeAbiVersion(): Int

    // ---- lifecycle -------------------------------------------------------

    /** `gc_create(seed)`; 0 on failure (or on an ABI mismatch). */
    external fun nativeCreate(seed: Int): Long

    /** `gc_destroy(h)`; safe with 0. */
    external fun nativeDestroy(handle: Long)

    // ---- geometry --------------------------------------------------------

    /** `gc_resize(h, fbW, fbH, safeLeft, safeTop, safeRight, safeBottom)`, pixels. */
    external fun nativeResize(
        handle: Long,
        fbWidth: Int,
        fbHeight: Int,
        safeLeft: Float,
        safeTop: Float,
        safeRight: Float,
        safeBottom: Float,
    )

    /** `gc_view_scale(h)`: pixels per virtual unit (never <= 0). */
    external fun nativeViewScale(handle: Long): Float

    // ---- simulation ------------------------------------------------------

    /**
     * `gc_update`.  The parameter order after `dt` mirrors `struct gc_input`
     * field for field: move_x, move_y, aim_x, aim_y, pointer_active,
     * pointer_down, buttons.
     */
    external fun nativeUpdate(
        handle: Long,
        dt: Float,
        moveX: Float,
        moveY: Float,
        aimX: Float,
        aimY: Float,
        pointerActive: Int,
        pointerDown: Int,
        buttons: Int,
    )

    // ---- draw commands ---------------------------------------------------

    /** Number of commands for the frame just simulated (`gc_cmds` count only). */
    external fun nativeCmdCount(handle: Long): Int

    /**
     * Packs up to [count] commands into [floats] / [ints] and returns how many
     * were written:
     *
     * ```
     * floats[i * 9 + 0] = x    floats[i * 9 + 5] = u0
     * floats[i * 9 + 1] = y    floats[i * 9 + 6] = v0
     * floats[i * 9 + 2] = w    floats[i * 9 + 7] = u1
     * floats[i * 9 + 3] = h    floats[i * 9 + 8] = v1
     * floats[i * 9 + 4] = rot  (clockwise radians)
     * ints[i * 4 + 0] = kind   ints[i * 4 + 2] = rgba  (0xAARRGGBB, straight alpha)
     * ints[i * 4 + 1] = sprite ints[i * 4 + 3] = flags
     * ```
     */
    external fun nativeFillCommands(
        handle: Long,
        count: Int,
        floats: FloatArray,
        ints: IntArray,
    ): Int

    // ---- events ----------------------------------------------------------

    /** Number of events produced by the frame just simulated. */
    external fun nativeEventCount(handle: Long): Int

    /** `floats[i * 3 + {0,1,2}] = x, y, value`; `ints[i] = type`; returns written. */
    external fun nativeFillEvents(
        handle: Long,
        count: Int,
        floats: FloatArray,
        ints: IntArray,
    ): Int

    // ---- status ----------------------------------------------------------

    /**
     * Fills `ints[0..6] = wave, level, kills, money, score, best_score, state`
     * and `floats[0..2] = player_hp, player_hp_max, time_alive`.
     * Returns 1 on success, 0 if the handle is null or an array is too small.
     */
    external fun nativeStatus(handle: Long, ints: IntArray, floats: FloatArray): Int

    // ---- save blob -------------------------------------------------------

    /** Returns bytes written into [out] (using [capacity]), or -1 if it does not fit. */
    external fun nativeSave(handle: Long, out: ByteArray, capacity: Int): Int

    /** Applies a previously saved blob; returns the core's status code. */
    external fun nativeLoad(handle: Long, data: ByteArray, length: Int): Int

    // ---- debug hook ------------------------------------------------------

    external fun nativeDebug(handle: Long, cmd: Int, value: Float)

    // ---- assets ----------------------------------------------------------

    /**
     * `[0 .. n-2]` = `gc_sprite_file(i)` for every [CMD_SPRITE] id,
     * `[n-1]` = the `gc_font_atlas` file name (the atlas is always last).
     * Called once per EGL surface creation; never on the frame path.
     */
    external fun nativeAssetNames(): Array<String?>
}

/**
 * A copy of `gc_status` for logging/diagnostics.  The core draws its own HUD, so
 * the shell only uses this to detect state transitions (autosave, log lines) and
 * to expose values for tests.  Deliberately built only when something changed —
 * never once per frame.
 */
data class GameStatus(
    val wave: Int,
    val level: Int,
    val kills: Int,
    val money: Int,
    val score: Int,
    val bestScore: Int,
    val state: Int,
    val playerHp: Float,
    val playerHpMax: Float,
    val timeAlive: Float,
) {
    val stateName: String
        get() = when (state) {
            NativeCore.STATE_TITLE -> "TITLE"
            NativeCore.STATE_PLAYING -> "PLAYING"
            NativeCore.STATE_LEVEL_UP -> "LEVEL_UP"
            NativeCore.STATE_SHOP -> "SHOP"
            NativeCore.STATE_PAUSED -> "PAUSED"
            NativeCore.STATE_GAME_OVER -> "GAME_OVER"
            else -> "UNKNOWN($state)"
        }
}
