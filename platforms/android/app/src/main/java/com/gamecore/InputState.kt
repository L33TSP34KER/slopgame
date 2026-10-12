package com.gamecore

import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/**
 * Platform-independent touch -> `gc_input` state machine.
 *
 * Deliberately free of Android imports so the stick maths can be reasoned about
 * (and unit-tested) on its own; [HudInput] is the thin `MotionEvent` adapter that
 * drives it.
 *
 * ## Layout (all proportions of the *physical* framebuffer, no density needed)
 *
 * ```
 *  +--------------------------------------+
 *  |                    |                 |
 *  |   LEFT HALF        |   RIGHT HALF    |
 *  |   floating move    |   floating aim  |
 *  |   joystick         |   stick         |
 *  |                    |        [ DASH ] |  <- bottom-right corner
 *  +--------------------------------------+
 * ```
 *
 * * stick radius   = 14% of min(width, height)
 * * dead zone      = 10% of that radius (radial)
 * * dash button    = 16% of min(width, height) square, 4% margin, bottom-right
 *
 * ## Coordinate conversion
 *
 * The core hands out a single scale (`gc_view_scale`), so the inverse of
 * `gc_pixels_to_virtual()` is a plain division -- including its `<= 0 -> 1`
 * guard, which is repeated here so Kotlin can never divide by zero even if a
 * resize has not happened yet.
 *
 * ## Pointer ownership
 *
 * Every gesture is tracked by **pointer id**, never by index: a finger that
 * started the move stick keeps it even if another finger is lifted first (which
 * renumbers `MotionEvent` indices but not ids), and a finger that started on the
 * dash button keeps it until *it* goes up, even if it slides off.  New touches
 * are only accepted by a role that is currently free.
 */
class InputState {

    // ---- the gc_input outputs (read by GameRenderer on the GL thread) ----

    /** Movement axis, -1..1, already dead-zoned and clamped to the unit circle. */
    var moveX: Float = 0f
        private set
    var moveY: Float = 0f
        private set

    /** Pointer position in VIRTUAL units (aim for the core's crosshair). */
    var aimX: Float = 0f
        private set
    var aimY: Float = 0f
        private set

    /** 1 once a pointer has ever been seen (a mouse/finger is known). */
    var pointerActive: Int = 0
        private set

    /** 1 while the aim finger is down; the core edge-detects taps from this. */
    var pointerDown: Int = 0
        private set

    /** Held GC_BTN_* bitmask. */
    var buttons: Int = 0
        private set

    // ---- geometry (pixels), recomputed by [resize] -----------------------

    private var viewportW = 1f
    private var viewportH = 1f
    private var pxPerVirtual = 1f

    /** Radius of the move stick in pixels. */
    var stickRadiusPx: Float = 0f
        private set

    /** Radial dead zone in pixels. */
    var deadZonePx: Float = 0f
        private set

    var dashLeft: Float = 0f
        private set
    var dashTop: Float = 0f
        private set
    var dashRight: Float = 0f
        private set
    var dashBottom: Float = 0f
        private set

    var dashPressed: Boolean = false
        private set

    // ---- live gesture state (pixels) -------------------------------------

    private var movePointerId = NO_POINTER
    private var aimPointerId = NO_POINTER
    private var dashPointerId = NO_POINTER

    private var moveOriginX = 0f
    private var moveOriginY = 0f

    /**
     * Origin (pixels) of the live move stick, for the shell's touch overlay.
     * Read-only: input state is only ever mutated on the GL thread.
     */
    val moveOriginXPx: Float
        get() = moveOriginX
    val moveOriginYPx: Float
        get() = moveOriginY

    /** Clamped nub position of the move stick (for the shell's touch overlay). */
    var moveNubX: Float = 0f
        private set
    var moveNubY: Float = 0f
        private set

    var moveActive: Boolean = false
        private set
    var aimActive: Boolean = false
        private set

    /** Origin of the aim stick in pixels (for the shell's touch overlay). */
    val aimOriginXPx: Float
        get() = aimOriginX
    val aimOriginYPx: Float
        get() = aimOriginY

    private var aimOriginX = 0f
    private var aimOriginY = 0f

    // ---------------------------------------------------------------------

    /**
     * Called from `GameRenderer.onSurfaceChanged` / `onDrawFrame` on the GL
     * thread with the physical pixel size and the current `gc_view_scale`.
     */
    fun resize(fbWidthPx: Int, fbHeightPx: Int, scalePxPerVirtual: Float) {
        viewportW = max(1f, fbWidthPx.toFloat())
        viewportH = max(1f, fbHeightPx.toFloat())
        pxPerVirtual = if (scalePxPerVirtual > 0f) scalePxPerVirtual else 1f

        val unit = min(viewportW, viewportH)
        stickRadiusPx = unit * STICK_RADIUS_FRACTION
        deadZonePx = stickRadiusPx * DEAD_ZONE_FRACTION

        val dashSize = unit * DASH_SIZE_FRACTION
        val margin = unit * DASH_MARGIN_FRACTION
        dashRight = viewportW - margin
        dashBottom = viewportH - margin
        dashLeft = dashRight - dashSize
        dashTop = dashBottom - dashSize

        // Keep an in-flight stick consistent with the new radius/origin.
        moveNubX = moveOriginX
        moveNubY = moveOriginY
    }

    /** `ACTION_DOWN` / `ACTION_POINTER_DOWN`. */
    fun onPointerDown(id: Int, x: Float, y: Float) {
        if (!inDashButton(x, y) && x < viewportW * 0.5f) {
            // ---- left half: floating move joystick, origin = first touch ----
            if (movePointerId == NO_POINTER) {
                movePointerId = id
                moveOriginX = x
                moveOriginY = y
                moveNubX = x
                moveNubY = y
                moveActive = true
                moveX = 0f
                moveY = 0f
            }
            return
        }

        if (inDashButton(x, y)) {
            if (dashPointerId == NO_POINTER) {
                dashPointerId = id
                dashPressed = true
                buttons = buttons or NativeCore.BTN_DASH
            }
            return
        }

        // ---- right half: floating aim stick -----------------------------
        if (aimPointerId == NO_POINTER) {
            aimPointerId = id
            aimOriginX = x
            aimOriginY = y
            aimActive = true
            setAimFromPixels(x, y)
            pointerActive = 1
            pointerDown = 1
        }
    }

    /** `ACTION_MOVE`: called for every pointer currently down. */
    fun onPointerMove(id: Int, x: Float, y: Float) {
        when (id) {
            movePointerId -> applyMoveStick(x, y)
            aimPointerId -> setAimFromPixels(x, y)
            dashPointerId -> { /* the button keeps ownership until it goes up */ }
            else -> { /* not ours (e.g. a third finger) */ }
        }
    }

    /** `ACTION_UP` / `ACTION_POINTER_UP`. */
    fun onPointerUp(id: Int, x: Float, y: Float) {
        when (id) {
            movePointerId -> {
                movePointerId = NO_POINTER
                moveActive = false
                moveX = 0f
                moveY = 0f
            }
            aimPointerId -> {
                aimPointerId = NO_POINTER
                aimActive = false
                // Keep pointer_active (the crosshair stays where it was left) but
                // drop the "down" edge so the core sees the release.
                pointerActive = 1
                pointerDown = 0
            }
            dashPointerId -> {
                dashPointerId = NO_POINTER
                dashPressed = false
                buttons = buttons and NativeCore.BTN_DASH.inv()
            }
            else -> { /* not ours */ }
        }
    }

    /**
     * `ACTION_CANCEL` (a parent stole the gesture, the window lost focus, ...):
     * drop every live finger but keep the pause toggle, which is not a touch.
     */
    fun onCancel() {
        movePointerId = NO_POINTER
        aimPointerId = NO_POINTER
        dashPointerId = NO_POINTER
        moveActive = false
        aimActive = false
        dashPressed = false
        moveX = 0f
        moveY = 0f
        pointerDown = 0
        // The pointer is still "known" as far as the core is concerned.
        pointerActive = 1
        buttons = buttons and NativeCore.BTN_DASH.inv()
    }

    /**
     * System Back button.  Held state, edge-detected by the core, so this simply
     * flips GC_BTN_PAUSE.  The shell deliberately never finishes the activity on
     * Back: the core's pause menu owns quitting.
     */
    fun togglePause() {
        buttons = buttons xor NativeCore.BTN_PAUSE
    }

    // ---------------------------------------------------------------------
    // internals
    // ---------------------------------------------------------------------

    private fun inDashButton(x: Float, y: Float): Boolean =
        x >= dashLeft && x <= dashRight && y >= dashTop && y <= dashBottom

    /**
     * Aim is the raw pointer position; the "stick" is only floating because its
     * origin is wherever the finger landed.  The core receives virtual units.
     */
    private fun setAimFromPixels(x: Float, y: Float) {
        aimX = x / pxPerVirtual
        aimY = y / pxPerVirtual
    }

    /**
     * Radial dead zone + clamp to the stick radius.
     *
     * `len` is the distance from the touch origin.  Inside the dead zone the axis
     * is exactly zero (no jitter); outside it the axis is the unit direction
     * scaled by `min(len / radius, 1)`, so the core gets an analogue value in
     * -1..1 that saturates at the stick radius.
     */
    private fun applyMoveStick(x: Float, y: Float) {
        val dx = x - moveOriginX
        val dy = y - moveOriginY
        val len = hypot(dx, dy)

        if (len <= deadZonePx || stickRadiusPx <= 0f) {
            moveX = 0f
            moveY = 0f
            moveNubX = moveOriginX
            moveNubY = moveOriginY
            return
        }

        val inv = 1f / len
        val ux = dx * inv
        val uy = dy * inv
        val magnitude = min(len / stickRadiusPx, 1f)

        moveX = ux * magnitude
        moveY = uy * magnitude

        // Nub position for the shell overlay (visual only).
        val nubLen = magnitude * stickRadiusPx
        moveNubX = moveOriginX + ux * nubLen
        moveNubY = moveOriginY + uy * nubLen
    }

    companion object {
        private const val NO_POINTER = -1

        /** Stick radius as a fraction of min(fbWidth, fbHeight). */
        const val STICK_RADIUS_FRACTION = 0.14f

        /** Dead zone as a fraction of the stick radius. */
        const val DEAD_ZONE_FRACTION = 0.10f

        const val DASH_SIZE_FRACTION = 0.16f
        const val DASH_MARGIN_FRACTION = 0.04f
    }
}
