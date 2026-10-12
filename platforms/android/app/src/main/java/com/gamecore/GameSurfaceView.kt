package com.gamecore

import android.annotation.SuppressLint
import android.content.Context
import android.opengl.GLSurfaceView
import android.os.Build
import android.util.Log
import android.view.MotionEvent
import android.view.WindowInsets
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * The window: a `GLSurfaceView` in continuous (vsync-driven) render mode plus the
 * shell-side input plumbing.
 *
 * ## Why continuous mode is not a busy loop
 *
 * `RENDERMODE_CONTINUOUSLY` makes `GLThread` render one frame per iteration and
 * block inside `eglSwapBuffers` until the display's vsync, so there is no spin,
 * no `Choreographer` callback and no hand-rolled `Thread.sleep`.  `onPause` /
 * `onResume` stop and restart that thread, which is the "render loop lifecycle"
 * the ABI expects.  `preserveEGLContextOnPause` keeps the EGL context (and with
 * it every texture and the shader program) alive across a normal pause; if the
 * driver still loses the context, `GameRenderer.onSurfaceCreated` rebuilds
 * everything.
 *
 * ## Touch events are marshalled to the GL thread
 *
 * `MotionEvent`s arrive on the UI thread, but `InputState` is read by the renderer
 * on the GL thread and the core is thread-affine.  Each event is therefore
 * `MotionEvent.obtain`-copied, posted with `queueEvent` and recycled after it has
 * been consumed on the GL thread.  That costs one small allocation per *touch
 * event* (not per frame) and removes every data race on the input state.
 */
class GameSurfaceView(
    context: Context,
    private val onFatal: (String) -> Unit = {},
) : GLSurfaceView(context) {

    private val inputState = InputState()
    private val hudInput = HudInput(inputState)
    private val saveStore = SaveStore(context)

    /** UI-thread-owned snapshot; replaced (never mutated) so the GL thread sees it safely. */
    @Volatile
    private var insetsSnapshot = FloatArray(4)

    private val renderer: GameRenderer

    /** Set while the GL thread is being asked to save, so repeat pauses are cheap. */
    @Volatile
    private var saveInFlight = false

    init {
        setEGLContextClientVersion(2) // OpenGL ES 2.0: widest device support
        preserveEGLContextOnPause = true

        renderer = GameRenderer(
            assets = context.assets,
            saveStore = saveStore,
            input = inputState,
            insetsProvider = { safeInsetsSnapshot() },
            onFatal = onFatal,
        )

        setRenderer(renderer)
        renderMode = RENDERMODE_CONTINUOUSLY

        isFocusable = true
        isFocusableInTouchMode = true

        setOnApplyWindowInsetsListener { _, insets ->
            updateInsets(insets)
            insets // not consumed: nothing below us needs different insets
        }
    }

    // =====================================================================
    // lifecycle
    // =====================================================================

    /**
     * Stops the render loop and persists the core's save blob first.
     *
     * The save happens on the GL thread (core thread affinity) and the UI thread
     * waits at most [SAVE_TIMEOUT_MS] for it: long enough for a 1 KiB prefs write,
     * short enough that a wedged GL thread can never ANR the activity.
     */
    override fun onPause() {
        saveNow()
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        // System bars may have changed while we were away; re-ask and re-resize.
        renderer.notifyInsetsChanged()
        requestApplyInsets()
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        requestApplyInsets()
    }

    override fun onDetachedFromWindow() {
        // Destroy the core handle on its owning thread.  GL objects are not
        // deleted here: the EGL context is going away anyway and the driver frees
        // them with it.
        queueEvent { renderer.shutdown() }
        super.onDetachedFromWindow()
    }

    // =====================================================================
    // input
    // =====================================================================

    @SuppressLint("ClickableViewAccessibility") // performClick() is overridden below
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.pointerCount == 0) {
            return true
        }
        val copy = MotionEvent.obtain(event)
        queueEvent {
            try {
                hudInput.onTouchEvent(copy)
            } finally {
                copy.recycle()
            }
        }
        return true
    }

    /** Required by the accessibility linter; the game has no click semantics. */
    override fun performClick(): Boolean = super.performClick()

    /**
     * Back button.  Always handled: it toggles `GC_BTN_PAUSE` instead of leaving
     * the game (see [HudInput.onBackPressed]).
     */
    fun handleBackPressed() {
        queueEvent { hudInput.onBackPressed() }
    }

    // =====================================================================
    // save
    // =====================================================================

    /** Blocking (bounded) save on the GL thread; safe to call repeatedly. */
    fun saveNow() {
        if (!isAttachedToWindow) {
            return
        }
        if (saveInFlight) {
            return
        }
        saveInFlight = true
        val latch = CountDownLatch(1)
        queueEvent {
            try {
                renderer.performSave(synchronous = true)
            } finally {
                saveInFlight = false
                latch.countDown()
            }
        }
        try {
            latch.await(SAVE_TIMEOUT_MS, TimeUnit.MILLISECONDS)
        } catch (e: InterruptedException) {
            Thread.currentThread().interrupt()
        } finally {
            saveInFlight = false
        }
    }

    // =====================================================================
    // insets
    // =====================================================================

    /**
     * Copy of the most recent safe-area insets in **pixels**, ordered
     * (left, top, right, bottom) to match `gc_resize`.  Called from the GL thread
     * by the renderer, hence the volatile snapshot rather than reading the view's
     * insets off the UI thread.
     */
    fun safeInsetsSnapshot(): FloatArray = insetsSnapshot.copyOf()

    @Suppress("DEPRECATION") // systemWindowInset* is the only API below API 30
    private fun updateInsets(insets: WindowInsets) {
        val out = FloatArray(4)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bars = insets.getInsets(
                WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout(),
            )
            out[0] = bars.left.toFloat()
            out[1] = bars.top.toFloat()
            out[2] = bars.right.toFloat()
            out[3] = bars.bottom.toFloat()
        } else {
            out[0] = insets.systemWindowInsetLeft.toFloat()
            out[1] = insets.systemWindowInsetTop.toFloat()
            out[2] = insets.systemWindowInsetRight.toFloat()
            out[3] = insets.systemWindowInsetBottom.toFloat()
        }
        insetsSnapshot = out
        renderer.notifyInsetsChanged()
        if (LOG_INSETS) {
            Log.d(TAG, "insets px = ${out[0]}, ${out[1]}, ${out[2]}, ${out[3]}")
        }
    }

    companion object {
        private const val TAG = "GameSurfaceView"
        private const val LOG_INSETS = false

        /** Upper bound on how long `onPause` may block for the save. */
        private const val SAVE_TIMEOUT_MS = 250L
    }
}
