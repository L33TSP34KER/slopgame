package com.gamecore

import android.view.MotionEvent

/**
 * `MotionEvent` -> [InputState] adapter: the Android half of the touch layer.
 *
 * It exists so [InputState] can stay free of Android types (and therefore
 * reviewable/testable on its own), and so that multi-touch bookkeeping is done
 * in exactly one place:
 *
 * * `ACTION_DOWN` / `ACTION_POINTER_DOWN` -> [InputState.onPointerDown]
 * * `ACTION_MOVE` -> [InputState.onPointerMove] for **every** pointer currently
 *   down (a MOVE event carries all of them, not just the one that moved)
 * * `ACTION_UP` / `ACTION_POINTER_UP` -> [InputState.onPointerUp]
 * * `ACTION_CANCEL` -> [InputState.onCancel]
 *
 * The pointer **id** (`getPointerId(index)`), never the index, is what identifies
 * a finger: indices are compacted as soon as any finger lifts, ids are not.
 *
 * All methods here run on the GL thread: `GameSurfaceView` copies each event with
 * `MotionEvent.obtain` and posts it through `queueEvent`, so [InputState] is only
 * ever read and written by the same thread that owns the core.
 */
class HudInput(private val state: InputState) {

    fun onTouchEvent(event: MotionEvent) {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN,
            MotionEvent.ACTION_POINTER_DOWN -> {
                val index = event.actionIndex
                state.onPointerDown(event.getPointerId(index), event.getX(index), event.getY(index))
            }

            MotionEvent.ACTION_MOVE -> {
                val pointers = event.pointerCount
                for (index in 0 until pointers) {
                    state.onPointerMove(
                        event.getPointerId(index),
                        event.getX(index),
                        event.getY(index),
                    )
                }
            }

            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_POINTER_UP -> {
                val index = event.actionIndex
                state.onPointerUp(event.getPointerId(index), event.getX(index), event.getY(index))
            }

            MotionEvent.ACTION_CANCEL -> state.onCancel()

            else -> {
                // ACTION_OUTSIDE / ACTION_SCROLL and friends are ignored.
            }
        }
    }

    /**
     * System Back button: a **toggle** of `GC_BTN_PAUSE` (held state, the core
     * edge-detects it).  The shell never finishes the activity on Back -- the
     * core's pause menu owns that decision.
     */
    fun onBackPressed() {
        state.togglePause()
    }
}
