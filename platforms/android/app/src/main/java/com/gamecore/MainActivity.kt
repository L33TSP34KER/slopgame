package com.gamecore

import android.app.Activity
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.util.Base64
import android.util.Log
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.widget.Toast

/**
 * The only Activity.  It owns a fullscreen immersive [GameSurfaceView] and does
 * nothing else -- there is no game logic, no HUD and no layout XML anywhere in
 * the shell, because the core emits everything as draw commands.
 *
 * Landscape, no action bar and the `orientation|screenSize|...` config changes are
 * declared in AndroidManifest.xml, so a rotation never recreates the Activity;
 * the surface is merely resized and `gc_resize` is called with the new physical
 * pixel size.
 */
class MainActivity : Activity() {

    private var gameView: GameSurfaceView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Load the JNI shim (which pulls in libgame_core.so) and refuse to run on
        // an ABI mismatch, exactly as include/game_core.h demands.
        if (NativeCore.loadFailure != null) {
            fail("native library failed to load: ${NativeCore.loadFailure?.message}")
            return
        }
        if (!checkAbi()) {
            return
        }

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val view = GameSurfaceView(this) { message ->
            // Called from the GL thread, which has no Looper: hop to the UI thread.
            runOnUiThread {
                Toast.makeText(this, message, Toast.LENGTH_LONG).show()
            }
        }
        gameView = view
        setContentView(view)
        // Only now does the window have a decor view: asking for the insets
        // controller any earlier throws on Android 14 (the framework calls
        // DecorView.getWindowInsetsController() on a null decor view).
        applyImmersiveMode()
    }

    override fun onResume() {
        super.onResume()
        applyImmersiveMode()
        gameView?.onResume()
    }

    override fun onPause() {
        // GameSurfaceView.onPause() saves first (bounded wait on the GL thread)
        // and then stops the render loop.
        gameView?.onPause()
        super.onPause()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) {
            // The system bars come back when the user swipes; hide them again.
            applyImmersiveMode()
        }
    }

    /**
     * Back toggles `GC_BTN_PAUSE` in the core (the pause menu owns quitting), so
     * the activity is never finished from here.
     */
    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        val view = gameView
        if (view != null) {
            view.handleBackPressed()
            return
        }
        super.onBackPressed()
    }

    // =====================================================================

    private fun checkAbi(): Boolean {
        return try {
            val abi = NativeCore.nativeAbiVersion()
            if (abi != NativeCore.EXPECTED_ABI_VERSION) {
                fail("libgame_core ABI mismatch: found $abi, expected ${NativeCore.EXPECTED_ABI_VERSION}")
                false
            } else {
                true
            }
        } catch (e: LinkageError) {
            // UnsatisfiedLinkError, ExceptionInInitializerError, NoClassDefFoundError
            fail("native library unavailable: $e")
            false
        }
    }

    private fun fail(message: String) {
        Log.e(TAG, message)
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        finish()
    }

    /**
     * Immersive sticky fullscreen: no status bar, no navigation bar, swipe to
     * reveal them temporarily.  The insets themselves are forwarded to the core
     * through `gc_resize` by GameSurfaceView.
     */
    @Suppress("DEPRECATION") // the pre-API-30 branch uses the deprecated systemUiVisibility flags
    private fun applyImmersiveMode() {
        // Fullscreen is a nicety: if a device refuses to cooperate the game must
        // still start, so the whole thing is best-effort.
        runCatching { applyImmersiveModeOrThrow() }
            .onFailure { Log.w(TAG, "immersive mode unavailable: ${it.message}") }
    }

    @Suppress("DEPRECATION")
    private fun applyImmersiveModeOrThrow() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(false)
            window.insetsController?.let { controller ->
                controller.hide(WindowInsets.Type.systemBars())
                controller.systemBarsBehavior =
                    WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            window.decorView.systemUiVisibility = (
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    or View.SYSTEM_UI_FLAG_FULLSCREEN
                    or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                )
        }
    }

    companion object {
        private const val TAG = "MainActivity"
    }
}

/**
 * The persisted `gc_save` blob, stored base64-encoded in `SharedPreferences`.
 *
 * The blob is opaque to the shell and its size is not knowable up front, so it is
 * stored as one string under one key.  Reads happen on the GL thread (when the
 * core is created); writes happen on the GL thread too, either from the 5 s
 * autosave or from `onPause`, where [store] is asked to commit synchronously.
 */
/*
 * Public (not `internal`) on purpose: GameRenderer takes a SaveStore as a
 * constructor parameter, and a public constructor must not expose a type with
 * lower visibility.
 */
class SaveStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    /** Returns the stored blob, or null when there is nothing (valid) to restore. */
    fun load(): ByteArray? {
        val encoded = prefs.getString(KEY_BLOB, null) ?: return null
        if (encoded.isEmpty()) {
            return null
        }
        return try {
            Base64.decode(encoded, Base64.NO_WRAP)
        } catch (e: IllegalArgumentException) {
            Log.w(TAG, "discarding corrupt save blob: ${e.message}")
            null
        }
    }

    /** Stores the blob; [synchronous] commits to disk instead of applying async. */
    fun store(blob: ByteArray, synchronous: Boolean) {
        if (blob.isEmpty()) {
            return
        }
        val encoded = Base64.encodeToString(blob, Base64.NO_WRAP)
        val editor = prefs.edit().putString(KEY_BLOB, encoded)
        if (synchronous) {
            editor.commit()
        } else {
            editor.apply()
        }
    }

    companion object {
        private const val TAG = "SaveStore"

        /** `SharedPreferences` file name; referenced by res/xml/backup_rules.xml. */
        const val PREFS_NAME = "game_native_save"
        private const val KEY_BLOB = "save_blob"
    }
}
