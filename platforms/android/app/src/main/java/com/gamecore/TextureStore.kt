package com.gamecore

import android.content.res.AssetManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.opengl.GLES20
import android.opengl.GLUtils
import android.util.Log
import android.util.SparseIntArray
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Owns every texture the frame needs: one per `gc_sprite_id`, the font atlas and
 * a 1x1 white texture.
 *
 * ## Keys
 *
 * A command's texture is looked up by an `Int` key that comes straight from the
 * command stream:
 *
 * * `0 .. GC_SPR_COUNT-1` -- a sprite id (`kind == GC_CMD_SPRITE`), see [KEY_ATLAS]
 * * [KEY_ATLAS] (`-1`)     -- the font atlas (`kind == GC_CMD_GLYPH`)
 * * `>= KEY_WHITE`         -- never used by commands; the white texture is fetched
 *   directly through [whiteTexture] for `GC_CMD_RECT` and the shell overlay.
 *
 * `SparseIntArray` (not `HashMap<Int, Int>`) so lookups never box or allocate.
 *
 * ## Straight alpha
 *
 * `gc_cmd::rgba` is *non-premultiplied*, so the textures must be too, otherwise
 * tinting and blending would double-multiply alpha.  `BitmapFactory` premultiplies
 * by default; we decode with `inPremultiplied = false` (API 19+) and, defensively,
 * un-premultiply anything that still reports `isPremultiplied`.
 *
 * ## Threading
 *
 * Every method must be called on the GL thread with a current context: GL object
 * names are context-local, and `onSurfaceCreated` (which is where [release] +
 * [loadAll] are called) runs again after a context loss.
 */
class TextureStore(private val assets: AssetManager) {

    /** key -> GL texture name.  0 means "not loaded yet". */
    // (Named `textureIds`, not `textures`: GameRenderer has a TextureStore called
    // `textures`, and sharing the word across both files reads badly.)
    private val textureIds = SparseIntArray()

    /** `[0 .. n-2]` sprite file names, `[n-1]` the atlas: the JNI asset table. */
    private var names: Array<String?> = emptyArray()

    private var whiteName = 0

    /**
     * Loads (or reloads) every asset.  A missing file is logged loudly and the
     * affected key falls back to the white texture, so a bad asset directory
     * degrades to visibly wrong colours instead of killing the GL thread.
     */
    fun loadAll(assetNames: Array<String?>) {
        names = assetNames

        // One opaque white texel, so GC_CMD_RECT can be drawn through exactly the
        // same shader path as a sprite (uUseTexture = 0 ignores the sample, but a
        // complete texture is bound either way).
        //
        // GLES20's `Buffer` arguments are raw pointers: the buffer MUST be
        // direct.  ByteBuffer.wrap() would throw "Must be a direct buffer", so the
        // single RGBA texel is written with absolute puts into a direct buffer
        // (position stays 0, so the whole 4-byte range is uploaded).
        val white = ByteBuffer.allocateDirect(BYTES_PER_TEXEL).order(ByteOrder.nativeOrder())
        white.put(0, 0xFF.toByte()) // R
        white.put(1, 0xFF.toByte()) // G
        white.put(2, 0xFF.toByte()) // B
        white.put(3, 0xFF.toByte()) // A
        whiteName = createTexture(1, 1, white, null)

        if (assetNames.isEmpty()) {
            Log.e(TAG, "core reported no asset names at all")
            return
        }
        val spriteCount = assetNames.size - 1
        for (index in 0 until spriteCount) {
            loadKey(index, assetNames[index])
        }
        loadKey(KEY_ATLAS, assetNames[spriteCount])
    }

    /**
     * GL texture name for a command's key.  Never allocates on a hit, and only
     * touches the disk once per key (which also makes it self-healing if the
     * context was lost without a matching [loadAll]).
     */
    fun textureFor(key: Int): Int {
        val existing = textureIds.get(key, 0)
        if (existing != 0) {
            return existing
        }
        val name = nameOf(key)
        if (name == null) {
            return whiteName
        }
        return loadKey(key, name)
    }

    fun whiteTexture(): Int = whiteName

    /** Number of sprite keys (the atlas is not counted). */
    val spriteCount: Int
        get() = if (names.isEmpty()) 0 else names.size - 1

    /**
     * Deletes every GL object.  Called at the top of `onSurfaceCreated`: the old
     * names belong to a context that no longer exists, so this only clears our
     * bookkeeping (glDelete* on a stale name is a no-op in the new context).
     */
    fun release() {
        val ints = IntArray(textureIds.size())
        for (i in 0 until textureIds.size()) {
            ints[i] = textureIds.valueAt(i)
        }
        if (ints.isNotEmpty()) {
            GLES20.glDeleteTextures(ints.size, ints, 0)
        }
        textureIds.clear()
        if (whiteName != 0) {
            GLES20.glDeleteTextures(1, intArrayOf(whiteName), 0)
            whiteName = 0
        }
    }

    // ---------------------------------------------------------------------

    private fun nameOf(key: Int): String? = when {
        key == KEY_ATLAS -> if (names.isEmpty()) null else names[names.size - 1]
        key >= 0 && key < spriteCount -> names[key]
        else -> null
    }

    private fun loadKey(key: Int, fileName: String?): Int {
        if (fileName == null) {
            Log.e(TAG, "asset for key $key is null in the core's asset table")
            return whiteName
        }
        return try {
            val name = decodeAndUpload(fileName)
            textureIds.put(key, name)
            name
        } catch (e: IOException) {
            Log.e(TAG, "cannot open asset '$fileName' for key $key: ${e.message}")
            whiteName
        } catch (e: RuntimeException) {
            Log.e(TAG, "cannot decode asset '$fileName' for key $key: ${e.message}")
            whiteName
        }
    }

    private fun decodeAndUpload(fileName: String): Int {
        val options = BitmapFactory.Options().apply {
            inPreferredConfig = Bitmap.Config.ARGB_8888
            inScaled = false
            // gc_cmd::rgba is straight (non-premultiplied) alpha; keep the PNG
            // bytes straight too so tint + GL_SRC_ALPHA blending stay correct.
            inPremultiplied = false
        }

        val bitmap: Bitmap = assets.open(fileName).use { stream ->
            BitmapFactory.decodeStream(stream, null, options)
        } ?: throw IOException("BitmapFactory returned null for '$fileName'")

        try {
            if (bitmap.isPremultiplied) {
                bitmap.setPremultiplied(false)
            }
            val name = createTexture(bitmap.width, bitmap.height, null, bitmap)
            Log.i(TAG, "uploaded '$fileName' (${bitmap.width}x${bitmap.height}) as texture $name")
            return name
        } finally {
            bitmap.recycle()
        }
    }

    /**
     * Uploads either a raw RGBA buffer or a [Bitmap] with
     * `GLUtils.texImage2D`, then applies bilinear filtering and edge clamping --
     * the ABI requires bilinear and there is no atlas bleeding protection other
     * than CLAMP_TO_EDGE, so both are mandatory.
     */
    private fun createTexture(
        width: Int,
        height: Int,
        pixels: ByteBuffer?,
        bitmap: Bitmap?,
    ): Int {
        val handles = IntArray(1)
        GLES20.glGenTextures(1, handles, 0)
        val name = handles[0]
        if (name == 0) {
            throw RuntimeException("glGenTextures returned 0")
        }
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, name)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)

        try {
            if (bitmap != null) {
                // GLUtils only understands these two configurations; anything else
                // throws, and loadKey() then falls back to the white texture.
                val config = bitmap.config
                if (config != Bitmap.Config.ARGB_8888 && config != Bitmap.Config.RGB_565) {
                    throw IllegalStateException(
                        "bitmap config $config is not uploadable (requested ARGB_8888)",
                    )
                }
                GLUtils.texImage2D(GLES20.GL_TEXTURE_2D, 0, bitmap, 0)
            } else if (pixels != null) {
                GLES20.glTexImage2D(
                    GLES20.GL_TEXTURE_2D, 0, GLES20.GL_RGBA, width, height, 0,
                    GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, pixels,
                )
            } else {
                throw IllegalArgumentException("createTexture needs pixels or a bitmap")
            }
        } catch (e: RuntimeException) {
            // Do not leak the name we just generated.
            GLES20.glDeleteTextures(1, intArrayOf(name), 0)
            GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, 0)
            throw e
        }

        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, 0)
        return name
    }

    companion object {
        private const val TAG = "TextureStore"

        /** Key for the font atlas.  Sprite keys are `0 .. n-1`, so -1 cannot collide. */
        const val KEY_ATLAS = -1

        /** One RGBA8 texel. */
        private const val BYTES_PER_TEXEL = 4
    }
}
