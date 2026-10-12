package com.gamecore

import android.content.res.AssetManager
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.util.Log
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import kotlin.math.cos
import kotlin.math.sin

/**
 * The whole Android renderer: drains `gc_cmds()` into GLES 2.0 draw calls.
 *
 * It contains no game logic, no camera, no text layout and no simulation; the
 * only maths here is "virtual units -> pixels -> NDC" and the per-quad rotation,
 * both of which the ABI explicitly pushes onto the renderer.
 *
 * ## One program, one shader path
 *
 * `aPos` (virtual units) + `aUV` + `aColor` (straight alpha) in, one texture
 * sampler.  `GC_CMD_RECT` is drawn with a 1x1 white texture bound and
 * `uUseTexture = 0`, so every batch uses the same program and the same vertex
 * layout and nothing has to be re-bound between kinds.
 *
 * The virtual->pixel mapping needs **only a scale**: commands are already in
 * screen space with the origin at the framebuffer's top-left and y pointing
 * down, exactly like the pixel space, so there is no offset, no letterbox and no
 * per-axis scale -- `pixel = virtual * gc_view_scale`.  The vertex shader is
 * therefore `uScale` (a vec2 whose components are equal) plus the unavoidable
 * pixel -> NDC step and y-flip; no matrix is needed.
 *
 * ## Batching
 *
 * Commands arrive in painter's order and must be drawn in that order, so the
 * renderer cannot sort.  It walks the list once and starts a new batch whenever
 * the batch key changes, where the key is `(texture, blend mode)`:
 *
 * * textures: the sprite PNG for `GC_CMD_SPRITE`, the atlas for `GC_CMD_GLYPH`,
 *   the white texture for `GC_CMD_RECT` and the shell overlay;
 * * blend: `GC_FLAG_FLASH` -> `GL_SRC_ALPHA, GL_ONE` (additive), everything else
 *   -> `GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA`.
 *
 * Per-command colour is a *vertex* attribute, not a uniform, precisely so that a
 * run of differently coloured rectangles/sprites still collapses into one draw.
 * `GC_FLAG_SHADOW` is handled on the CPU while batching: a black offset copy of
 * the quad is appended immediately before the real quad, which lands it
 * underneath (vertex order is preserved within a batch) at no extra draw call.
 *
 * All batches of the frame live in one growable direct [FloatBuffer]; the frame
 * uploads them with a single `glBufferData` and then issues one
 * `glDrawArrays(GL_TRIANGLES, first, count)` per batch.
 *
 * ## Allocation discipline
 *
 * The steady-state frame allocates nothing: the vertex buffer, the batch arrays,
 * the command/event staging arrays and the status arrays are all reused and only
 * grown when the core reports more work than they can hold.  (Strings, `Log`
 * calls, `GameStatus` objects and the save blob are only created on state
 * changes -- never per frame.)
 *
 * ## Threading
 *
 * Every `NativeCore` call and every touch mutation happens on the GL thread
 * (`GameSurfaceView` marshals `MotionEvent`s through `queueEvent`).  GL objects
 * are recreated from scratch in [onSurfaceCreated] because the EGL context -- and
 * with it every texture/program/buffer name -- may have been destroyed.
 */
class GameRenderer(
    private val assets: AssetManager,
    private val saveStore: SaveStore,
    private val input: InputState,
    private val insetsProvider: () -> FloatArray,
    private val onFatal: (String) -> Unit = {},
) : GLSurfaceView.Renderer {

    // ---- core handle -----------------------------------------------------
    private var handle: Long = 0L
    private var coreDisabled = false
    private var saveRestored = false

    // ---- GL objects ------------------------------------------------------
    private var program = 0
    private var vbo = 0

    private var uScale = -1
    private var uViewport = -1
    private var uUseTexture = -1
    private var uTexture = -1

    private val textures = TextureStore(assets)

    // ---- framebuffer -----------------------------------------------------
    private var fbWidth = 0
    private var fbHeight = 0
    private var viewScale = 1f

    @Volatile
    private var resizePending = true

    // ---- vertex staging --------------------------------------------------
    private var vertices: FloatBuffer = newVertexBuffer(INITIAL_VERTICES * VERTEX_FLOATS)
    private var vertexCount = 0

    private var batchFirst = IntArray(INITIAL_BATCHES)
    private var batchLength = IntArray(INITIAL_BATCHES)
    private var batchTexture = IntArray(INITIAL_BATCHES)
    private var batchAdditive = BooleanArray(INITIAL_BATCHES)
    private var batchCount = 0
    private var currentBatch = -1

    // ---- command / event staging ----------------------------------------
    private var cmdFloats = FloatArray(INITIAL_COMMANDS * NativeCore.FLOATS_PER_CMD)
    private var cmdInts = IntArray(INITIAL_COMMANDS * NativeCore.INTS_PER_CMD)
    private var eventFloats = FloatArray(INITIAL_EVENTS * NativeCore.FLOATS_PER_EVENT)
    private var eventInts = IntArray(INITIAL_EVENTS * NativeCore.INTS_PER_EVENT)
    private val statusInts = IntArray(NativeCore.STATUS_INTS)
    private val statusFloats = FloatArray(NativeCore.STATUS_FLOATS)

    // ---- timing / save ---------------------------------------------------
    private var lastFrameNanos = 0L
    private var lastSaveNanos = 0L
    private var statusTick = 0
    private var lastState = Int.MIN_VALUE
    private var statusSnapshot: IntArray = IntArray(NativeCore.STATUS_INTS)
    private var statusSnapshotFloats: FloatArray = FloatArray(NativeCore.STATUS_FLOATS)
    private var saveScratch = ByteArray(SAVE_INITIAL_BYTES)

    @Volatile
    private var shutdownRequested = false

    /** Latest status snapshot, for diagnostics/tests.  Null until polled. */
    @Volatile
    var lastStatus: GameStatus? = null
        private set

    /** Frames drawn since creation; diagnostics only. */
    @Volatile
    var frameNumber: Long = 0L
        private set

    // =====================================================================
    // GLSurfaceView.Renderer
    // =====================================================================

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        // A *new* context means every previously created name is meaningless.
        // Releasing first is safe: glDelete* on unknown names is a no-op, and
        // nothing has been created in this context yet.
        releaseGl()

        if (shutdownRequested) {
            return
        }

        try {
            program = buildProgram()
        } catch (e: RuntimeException) {
            coreDisabled = true
            Log.e(TAG, "shader setup failed", e)
            onFatal("Shader setup failed: ${e.message}")
            return
        }

        uScale = GLES20.glGetUniformLocation(program, "uScale")
        uViewport = GLES20.glGetUniformLocation(program, "uViewport")
        uUseTexture = GLES20.glGetUniformLocation(program, "uUseTexture")
        uTexture = GLES20.glGetUniformLocation(program, "uTexture")

        val buffers = IntArray(1)
        GLES20.glGenBuffers(1, buffers, 0)
        vbo = buffers[0]
        if (vbo == 0) {
            coreDisabled = true
            onFatal("glGenBuffers failed")
            return
        }

        textures.loadAll(NativeCore.nativeAssetNames())
        // Sound samples are optional (assets/sfx/*.ogg); this probes for them
        // once per surface on the GL thread and is a no-op when they are absent.

        GLES20.glDisable(GLES20.GL_DEPTH_TEST)
        GLES20.glDisable(GLES20.GL_CULL_FACE) // quads may be mirrored by negative sizes
        GLES20.glDisable(GLES20.GL_DITHER)
        GLES20.glEnable(GLES20.GL_BLEND)
        GLES20.glBlendFunc(GLES20.GL_SRC_ALPHA, GLES20.GL_ONE_MINUS_SRC_ALPHA)
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0)
        GLES20.glClearColor(0f, 0f, 0f, 1f)

        createCore()
        lastFrameNanos = 0L
        resizePending = true
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        GLES20.glViewport(0, 0, width, height)
        fbWidth = width
        fbHeight = height
        applyResize()
    }

    override fun onDrawFrame(gl: GL10?) {
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)

        if (shutdownRequested) {
            shutdownInternal()
            return
        }
        if (coreDisabled || program == 0 || vbo == 0) {
            return
        }
        if (handle == 0L) {
            // ABI mismatch or gc_create failure: onFatal already told the user.
            return
        }

        if (resizePending && fbWidth > 0 && fbHeight > 0) {
            applyResize()
        }

        // ---- real dt, from the GL thread's own clock --------------------
        val now = System.nanoTime()
        var dt = if (lastFrameNanos == 0L) 0f else (now - lastFrameNanos) / 1_000_000_000f
        lastFrameNanos = now
        // The core clamps internally too; this only avoids handing it a huge
        // first frame after a pause.  In continuous render mode the thread blocks
        // in eglSwapBuffers on vsync, so this loop never busy-spins.
        if (dt > MAX_DT_SECONDS) {
            dt = MAX_DT_SECONDS
        }
        if (dt < 0f) {
            dt = 0f
        }

        // ---- simulate ----------------------------------------------------
        // Input is written on this thread only (GameSurfaceView marshals touch
        // events through queueEvent), so these reads need no locking.
        NativeCore.nativeUpdate(
            handle, dt,
            input.moveX, input.moveY,
            input.aimX, input.aimY,
            input.pointerActive, input.pointerDown,
            input.buttons,
        )

        drawFrame()

        dispatchEvents()
        pollStatus()
        maybeAutosave(now)

        frameNumber++
    }

    // =====================================================================
    // public shell API (all called on the GL thread unless noted)
    // =====================================================================

    /**
     * Saves the opaque blob into SharedPreferences.  Called through
     * `GLSurfaceView.queueEvent` from [GameSurfaceView.saveNow] (Activity
     * onPause) and from the autosave path.
     *
     * [synchronous] commits the SharedPreferences write instead of applying it
     * asynchronously, so the blob is on disk before the process can be killed.
     */
    fun performSave(synchronous: Boolean) {
        val h = handle
        if (h == 0L) {
            return
        }
        val blob = readSaveBlob(h) ?: return
        saveStore.store(blob, synchronous)
        lastSaveNanos = System.nanoTime()
    }

    /** Marks this view's safe-area insets as stale so the next frame resizes. */
    fun notifyInsetsChanged() {
        resizePending = true
    }

    /**
     * Called from `queueEvent` when the view is detached.  The core handle is
     * destroyed on the GL thread (its owning thread) on the next frame; GL
     * objects are not deleted here because the context may already be gone (the
     * driver frees them with the context anyway).
     */
    fun shutdown() {
        shutdownRequested = true
    }

    // =====================================================================
    // frame composition
    // =====================================================================

    private fun drawFrame() {
        val commandCount = NativeCore.nativeCmdCount(handle)

        beginFrame()

        if (commandCount > 0) {
            ensureCommandCapacity(commandCount)
            val written = NativeCore.nativeFillCommands(
                handle, commandCount, cmdFloats, cmdInts,
            )
            for (i in 0 until written) {
                emitCommand(i)
            }
        }

        emitTouchOverlay()
        flushBatches()
    }

    private fun beginFrame() {
        vertexCount = 0
        batchCount = 0
        currentBatch = -1
        vertices.position(0)
        vertices.limit(vertices.capacity())
    }

    /** Builds batches from the staged command arrays. */
    private fun emitCommand(index: Int) {
        val f = index * NativeCore.FLOATS_PER_CMD
        val n = index * NativeCore.INTS_PER_CMD

        val kind = cmdInts[n]
        val sprite = cmdInts[n + 1]
        val rgba = cmdInts[n + 2]
        val flags = cmdInts[n + 3]

        val x = cmdFloats[f]
        val y = cmdFloats[f + 1]
        val w = cmdFloats[f + 2]
        val h = cmdFloats[f + 3]
        val rot = cmdFloats[f + 4]

        val alpha = ((rgba ushr 24) and 0xFF) / 255f
        if (alpha <= 0f || w == 0f || h == 0f) {
            return
        }
        val red = ((rgba ushr 16) and 0xFF) / 255f
        val green = ((rgba ushr 8) and 0xFF) / 255f
        val blue = (rgba and 0xFF) / 255f

        // Texture + UVs.  Sprites and rects always use the full [0,1] UV square;
        // only glyphs carry a (normalised) atlas sub-rect.
        val texture: Int
        val u0: Float
        val v0: Float
        val u1: Float
        val v1: Float
        when (kind) {
            NativeCore.CMD_GLYPH -> {
                texture = textures.textureFor(TextureStore.KEY_ATLAS)
                u0 = cmdFloats[f + 5]
                v0 = cmdFloats[f + 6]
                u1 = cmdFloats[f + 7]
                v1 = cmdFloats[f + 8]
            }
            NativeCore.CMD_SPRITE -> {
                texture = textures.textureFor(sprite)
                u0 = 0f; v0 = 0f; u1 = 1f; v1 = 1f
            }
            else -> { // GC_CMD_RECT and anything unknown: solid colour
                texture = textures.whiteTexture()
                u0 = 0f; v0 = 0f; u1 = 1f; v1 = 1f
            }
        }

        val additive = (flags and NativeCore.FLAG_FLASH) != 0

        // Rotation is applied on the CPU; see writeQuad for the matrix.  cos/sin
        // are computed once per command and shared by the shadow and the quad.
        val c: Float
        val s: Float
        if (rot == 0f) {
            c = 1f
            s = 0f
        } else {
            c = cos(rot)
            s = sin(rot)
        }

        if ((flags and NativeCore.FLAG_SHADOW) != 0) {
            // Soft dark copy underneath: same size/rotation, offset down-right in
            // *virtual* units (so it scales with the framebuffer, not the asset),
            // black, alpha proportional to the source so faded text fades too.
            // It inherits the command's blend mode: additive + black adds nothing,
            // which is the desired no-op for a flash that also asks for a shadow.
            appendQuad(
                texture, additive,
                x + SHADOW_OFFSET_VIRTUAL, y + SHADOW_OFFSET_VIRTUAL,
                w, h, c, s, u0, v0, u1, v1,
                0f, 0f, 0f, alpha * SHADOW_ALPHA_SCALE,
            )
        }

        appendQuad(
            texture, additive,
            x, y, w, h, c, s, u0, v0, u1, v1,
            red, green, blue, alpha,
        )
    }

    /**
     * Shell-drawn touch affordances (dash button, stick rings).  These are *not*
     * part of the core's command list: the core does not know where the shell's
     * floating sticks are.  They use the same white texture + rect path, so they
     * cost at most two more draw calls and never touch the core's batches.
     */
    private fun emitTouchOverlay() {
        if (!DRAW_TOUCH_OVERLAY || viewScale <= 0f) {
            return
        }
        val white = textures.whiteTexture()

        // DASH button (always visible, brighter while held).
        val dashW = (input.dashRight - input.dashLeft) / viewScale
        val dashH = (input.dashBottom - input.dashTop) / viewScale
        if (dashW > 0f && dashH > 0f) {
            val dashCx = (input.dashLeft + input.dashRight) * 0.5f / viewScale
            val dashCy = (input.dashTop + input.dashBottom) * 0.5f / viewScale
            val dashAlpha = if (input.dashPressed) 0.42f else 0.16f
            appendQuad(
                white, false, dashCx, dashCy, dashW, dashH, 1f, 0f,
                0f, 0f, 1f, 1f, 1f, 1f, 1f, dashAlpha,
            )
        }

        // Move-stick base + nub while the left finger is down.
        if (input.moveActive) {
            val r = input.stickRadiusPx / viewScale
            val baseX = input.moveOriginXPx / viewScale
            val baseY = input.moveOriginYPx / viewScale
            appendQuad(
                white, false, baseX, baseY, r * 2f, r * 2f, 1f, 0f,
                0f, 0f, 1f, 1f, 1f, 1f, 1f, 0.10f,
            )
            val nubX = input.moveNubX / viewScale
            val nubY = input.moveNubY / viewScale
            val nubR = r * 0.35f
            appendQuad(
                white, false, nubX, nubY, nubR * 2f, nubR * 2f, 1f, 0f,
                0f, 0f, 1f, 1f, 1f, 0.85f, 0.35f, 0.55f,
            )
        }

        // Aim marker (a small diamond, hence the 45 degree rotation) plus the base
        // of the floating aim stick, which is only visible while a finger is down.
        if (input.aimActive) {
            val baseR = input.stickRadiusPx / viewScale
            appendQuad(
                white, false,
                input.aimOriginXPx / viewScale, input.aimOriginYPx / viewScale,
                baseR * 2f, baseR * 2f, 1f, 0f,
                0f, 0f, 1f, 1f, 1f, 1f, 1f, 0.08f,
            )
            val r = AIM_MARKER_VIRTUAL
            appendQuad(
                white, false, input.aimX, input.aimY, r * 2f, r * 2f,
                COS_45, SIN_45, 0f, 0f, 1f, 1f, 1f, 0.35f, 0.35f, 0.6f,
            )
        }
    }

    // =====================================================================
    // batching
    // =====================================================================

    private fun startBatch(texture: Int, additive: Boolean) {
        val index = batchCount
        ensureBatchCapacity(index + 1)
        batchFirst[index] = vertexCount
        batchLength[index] = 0
        batchTexture[index] = texture
        batchAdditive[index] = additive
        batchCount = index + 1
        currentBatch = index
    }

    /**
     * Appends one quad, extending the current batch when the key still matches
     * and starting a new one otherwise.
     *
     * (c, s) is the pre-computed cos/sin of the command's rotation.
     */
    private fun appendQuad(
        texture: Int,
        additive: Boolean,
        cx: Float,
        cy: Float,
        w: Float,
        h: Float,
        c: Float,
        s: Float,
        u0: Float,
        v0: Float,
        u1: Float,
        v1: Float,
        red: Float,
        green: Float,
        blue: Float,
        alpha: Float,
    ) {
        if (currentBatch < 0 ||
            batchTexture[currentBatch] != texture ||
            batchAdditive[currentBatch] != additive
        ) {
            startBatch(texture, additive)
        }

        ensureVertexCapacity(vertexCount + VERTICES_PER_QUAD)

        val halfW = w * 0.5f
        val halfH = h * 0.5f

        // Local, unrotated corner offsets, clockwise from the top-left of the
        // quad in the y-down space the ABI uses.
        //
        // Rotation: gc_cmd::rot is CLOCKWISE about the quad's centre.  In a
        // y-down coordinate system the matrix
        //
        //     [ c  -s ]        x' = c*dx - s*dy
        //     [ s   c ]        y' = s*dx + c*dy
        //
        // rotates (dx, dy) clockwise on screen (the same matrix would be
        // counter-clockwise in a y-up space).  Scaling is uniform, so rotating in
        // virtual units and scaling to pixels afterwards is identical to
        // rotating in pixels.
        val x0 = -halfW; val y0 = -halfH
        val x1 = halfW; val y1 = -halfH
        val x2 = halfW; val y2 = halfH
        val x3 = -halfW; val y3 = halfH

        val wx0 = cx + (c * x0 - s * y0); val wy0 = cy + (s * x0 + c * y0)
        val wx1 = cx + (c * x1 - s * y1); val wy1 = cy + (s * x1 + c * y1)
        val wx2 = cx + (c * x2 - s * y2); val wy2 = cy + (s * x2 + c * y2)
        val wx3 = cx + (c * x3 - s * y3); val wy3 = cy + (s * x3 + c * y3)

        val base = vertexCount * VERTEX_FLOATS

        // Two triangles, no index buffer: 0,1,2 and 0,2,3.
        putVertex(base + 0 * VERTEX_FLOATS, wx0, wy0, u0, v0, red, green, blue, alpha)
        putVertex(base + 1 * VERTEX_FLOATS, wx1, wy1, u1, v0, red, green, blue, alpha)
        putVertex(base + 2 * VERTEX_FLOATS, wx2, wy2, u1, v1, red, green, blue, alpha)
        putVertex(base + 3 * VERTEX_FLOATS, wx0, wy0, u0, v0, red, green, blue, alpha)
        putVertex(base + 4 * VERTEX_FLOATS, wx2, wy2, u1, v1, red, green, blue, alpha)
        putVertex(base + 5 * VERTEX_FLOATS, wx3, wy3, u0, v1, red, green, blue, alpha)

        vertexCount += VERTICES_PER_QUAD
        batchLength[currentBatch] += VERTICES_PER_QUAD
        if (vertexCount + VERTICES_PER_QUAD > MAX_VERTICES_PER_FRAME) {
            // Pathological command stream: draw what has been batched so far and
            // keep going in a fresh buffer rather than growing without bound.
            Log.e(TAG, "vertex budget exhausted ($vertexCount vertices) -- flushing early")
            flushBatches()
            beginFrame()
        }
    }

    /** Vertex layout: x, y, u, v, r, g, b, a. */
    private fun putVertex(
        offset: Int,
        x: Float,
        y: Float,
        u: Float,
        v: Float,
        r: Float,
        g: Float,
        b: Float,
        a: Float,
    ) {
        vertices.put(offset + 0, x)
        vertices.put(offset + 1, y)
        vertices.put(offset + 2, u)
        vertices.put(offset + 3, v)
        vertices.put(offset + 4, r)
        vertices.put(offset + 5, g)
        vertices.put(offset + 6, b)
        vertices.put(offset + 7, a)
    }

    /**
     * Uploads the frame's vertices once and issues one `glDrawArrays` per batch.
     * Textures are bound only when they change; blend state likewise.
     */
    private fun flushBatches() {
        if (batchCount == 0 || vertexCount == 0) {
            return
        }
        if (program == 0 || vbo == 0) {
            return
        }

        GLES20.glUseProgram(program)
        GLES20.glUniform2f(uScale, viewScale, viewScale)
        GLES20.glUniform2f(uViewport, fbWidth.toFloat(), fbHeight.toFloat())
        GLES20.glUniform1i(uTexture, 0)
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0)

        uploadVertices()
        bindVertexAttributes()

        var boundTexture = -1
        var boundAdditive = false
        var blendKnown = false

        for (i in 0 until batchCount) {
            val texture = batchTexture[i]
            val additive = batchAdditive[i]

            if (texture != boundTexture) {
                GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, texture)
                // Only the white texture (rects + overlay) is sampled as a solid
                // colour; every other batch samples the bound PNG/atlas.
                GLES20.glUniform1i(
                    uUseTexture,
                    if (texture == textures.whiteTexture()) 0 else 1,
                )
                boundTexture = texture
            }
            if (!blendKnown || additive != boundAdditive) {
                if (additive) {
                    // GC_FLAG_FLASH: additive (muzzle flashes, hit sparks).
                    GLES20.glBlendFunc(GLES20.GL_SRC_ALPHA, GLES20.GL_ONE)
                } else {
                    GLES20.glBlendFunc(GLES20.GL_SRC_ALPHA, GLES20.GL_ONE_MINUS_SRC_ALPHA)
                }
                boundAdditive = additive
                blendKnown = true
            }

            GLES20.glDrawArrays(GLES20.GL_TRIANGLES, batchFirst[i], batchLength[i])
        }

        GLES20.glDisableVertexAttribArray(ATTRIB_POSITION)
        GLES20.glDisableVertexAttribArray(ATTRIB_UV)
        GLES20.glDisableVertexAttribArray(ATTRIB_COLOR)
    }

    private fun uploadVertices() {
        val floats = vertexCount * VERTEX_FLOATS
        vertices.position(0)
        vertices.limit(floats)
        GLES20.glBindBuffer(GLES20.GL_ARRAY_BUFFER, vbo)
        GLES20.glBufferData(
            GLES20.GL_ARRAY_BUFFER,
            floats * BYTES_PER_FLOAT,
            vertices,
            GLES20.GL_DYNAMIC_DRAW,
        )
        // Absolute put(index, value) requires index < limit(), so the limit must
        // go back to the full capacity before the next frame writes vertices.
        vertices.limit(vertices.capacity())
    }

    private fun bindVertexAttributes() {
        GLES20.glBindBuffer(GLES20.GL_ARRAY_BUFFER, vbo)
        GLES20.glEnableVertexAttribArray(ATTRIB_POSITION)
        GLES20.glVertexAttribPointer(
            ATTRIB_POSITION, 2, GLES20.GL_FLOAT, false, VERTEX_STRIDE_BYTES, 0,
        )
        GLES20.glEnableVertexAttribArray(ATTRIB_UV)
        GLES20.glVertexAttribPointer(
            ATTRIB_UV, 2, GLES20.GL_FLOAT, false, VERTEX_STRIDE_BYTES, 2 * BYTES_PER_FLOAT,
        )
        GLES20.glEnableVertexAttribArray(ATTRIB_COLOR)
        GLES20.glVertexAttribPointer(
            ATTRIB_COLOR, 4, GLES20.GL_FLOAT, false, VERTEX_STRIDE_BYTES, 4 * BYTES_PER_FLOAT,
        )
    }

    // =====================================================================
    // events -> audio
    // =====================================================================

    private fun dispatchEvents() {
        val count = NativeCore.nativeEventCount(handle)
        if (count <= 0) {
            return
        }
        ensureEventCapacity(count)
        val written = NativeCore.nativeFillEvents(handle, count, eventFloats, eventInts)
        for (i in 0 until written) {
            val f = i * NativeCore.FLOATS_PER_EVENT
        }
    }

    // =====================================================================
    // status / autosave
    // =====================================================================

    /**
     * `gc_status_get` is only needed to notice state transitions (autosave, log
     * lines), because the core draws its own HUD.  Polling is throttled and a
     * [GameStatus] is only allocated when something actually changed.
     */
    private fun pollStatus() {
        statusTick++
        if (statusTick < STATUS_POLL_FRAMES) {
            return
        }
        statusTick = 0

        if (NativeCore.nativeStatus(handle, statusInts, statusFloats) == 0) {
            return
        }

        var changed = false
        for (i in statusInts.indices) {
            if (statusInts[i] != statusSnapshot[i]) {
                changed = true
                break
            }
        }
        if (!changed) {
            for (i in statusFloats.indices) {
                if (statusFloats[i] != statusSnapshotFloats[i]) {
                    changed = true
                    break
                }
            }
        }
        if (!changed) {
            return
        }
        System.arraycopy(statusInts, 0, statusSnapshot, 0, statusInts.size)
        System.arraycopy(statusFloats, 0, statusSnapshotFloats, 0, statusFloats.size)

        val status = GameStatus(
            wave = statusInts[0],
            level = statusInts[1],
            kills = statusInts[2],
            money = statusInts[3],
            score = statusInts[4],
            bestScore = statusInts[5],
            state = statusInts[6],
            playerHp = statusFloats[0],
            playerHpMax = statusFloats[1],
            timeAlive = statusFloats[2],
        )
        lastStatus = status

        if (status.state != lastState) {
            Log.i(
                TAG,
                "state ${stateName(lastState)} -> ${stateName(status.state)} " +
                    "wave=${status.wave} score=${status.score} hp=${status.playerHp}",
            )
            lastState = status.state
            // A transition is the cheapest reliable moment to persist progress.
            performSave(synchronous = false)
        }
    }

    private fun maybeAutosave(now: Long) {
        if (lastSaveNanos == 0L) {
            lastSaveNanos = now
            return
        }
        if (now - lastSaveNanos >= AUTOSAVE_INTERVAL_NANOS) {
            performSave(synchronous = false)
            lastSaveNanos = now
        }
    }

    // =====================================================================
    // core lifecycle
    // =====================================================================

    private fun createCore() {
        val abi = NativeCore.nativeAbiVersion()
        if (abi != NativeCore.EXPECTED_ABI_VERSION) {
            coreDisabled = true
            val message = "libgame_core ABI $abi != expected ${NativeCore.EXPECTED_ABI_VERSION}"
            Log.e(TAG, message)
            onFatal(message)
            return
        }

        val seed = (System.nanoTime() and 0x7FFFFFFFL).toInt()
        val h = NativeCore.nativeCreate(seed)
        if (h == 0L) {
            coreDisabled = true
            val message = "gc_create failed (seed=$seed)"
            Log.e(TAG, message)
            onFatal(message)
            return
        }
        handle = h

        // Restore the persisted blob exactly once, on the thread that owns the
        // core (SharedPreferences is read here rather than on the UI thread).
        if (!saveRestored) {
            saveRestored = true
            val blob = saveStore.load()
            if (blob != null && blob.isNotEmpty()) {
                val rc = NativeCore.nativeLoad(handle, blob, blob.size)
                Log.i(TAG, "restored ${blob.size} bytes of save data (rc=$rc)")
            }
        }
    }

    private fun applyResize() {
        if (fbWidth <= 0 || fbHeight <= 0) {
            return
        }
        resizePending = false
        if (handle == 0L) {
            return
        }

        // Safe-area insets in PIXELS, straight from the window (already converted
        // by GameSurfaceView on the UI thread).
        val insets = insetsProvider()
        NativeCore.nativeResize(
            handle, fbWidth, fbHeight,
            insets[0], insets[1], insets[2], insets[3],
        )

        val scale = NativeCore.nativeViewScale(handle)
        viewScale = if (scale > 0f) scale else 1f
        input.resize(fbWidth, fbHeight, viewScale)
    }

    private fun shutdownInternal() {
        if (handle != 0L) {
            NativeCore.nativeDestroy(handle)
            handle = 0L
        }
        coreDisabled = true
    }

    // =====================================================================
    // save blob helpers
    // =====================================================================

    /**
     * `gc_save` has no "how big do I need?" query: it returns -1 when the blob
     * does not fit.  So we start at [SAVE_INITIAL_BYTES] and double up to
     * [SAVE_MAX_BYTES].  Only called off the frame path (autosave/pause).
     */
    private fun readSaveBlob(h: Long): ByteArray? {
        var capacity = saveScratch.size
        while (true) {
            if (saveScratch.size < capacity) {
                saveScratch = ByteArray(capacity)
            }
            val written = NativeCore.nativeSave(h, saveScratch, capacity)
            if (written >= 0) {
                return if (written == 0) null else saveScratch.copyOf(written)
            }
            if (capacity >= SAVE_MAX_BYTES) {
                Log.w(TAG, "gc_save still failed at $capacity bytes; skipping save")
                return null
            }
            capacity = minOf(capacity * 2, SAVE_MAX_BYTES)
        }
    }

    // =====================================================================
    // GL resource management
    // =====================================================================

    private fun releaseGl() {
        if (program != 0) {
            GLES20.glDeleteProgram(program)
            program = 0
        }
        if (vbo != 0) {
            val buffers = IntArray(1)
            buffers[0] = vbo
            GLES20.glDeleteBuffers(1, buffers, 0)
            vbo = 0
        }
        textures.release()
        uScale = -1
        uViewport = -1
        uUseTexture = -1
        uTexture = -1
        batchCount = 0
        vertexCount = 0
        currentBatch = -1
    }

    private fun buildProgram(): Int {
        val vertexShader = compileShader(GLES20.GL_VERTEX_SHADER, VERTEX_SHADER_SOURCE)
        val fragmentShader = compileShader(GLES20.GL_FRAGMENT_SHADER, FRAGMENT_SHADER_SOURCE)

        val prog = GLES20.glCreateProgram()
        if (prog == 0) {
            throw RuntimeException("glCreateProgram() returned 0")
        }
        GLES20.glAttachShader(prog, vertexShader)
        GLES20.glAttachShader(prog, fragmentShader)

        // Explicit locations: no glGetAttribLocation round trip, no ambiguity.
        GLES20.glBindAttribLocation(prog, ATTRIB_POSITION, "aPos")
        GLES20.glBindAttribLocation(prog, ATTRIB_UV, "aUV")
        GLES20.glBindAttribLocation(prog, ATTRIB_COLOR, "aColor")

        GLES20.glLinkProgram(prog)
        val status = IntArray(1)
        GLES20.glGetProgramiv(prog, GLES20.GL_LINK_STATUS, status, 0)
        if (status[0] == 0) {
            val log = GLES20.glGetProgramInfoLog(prog)
            GLES20.glDeleteProgram(prog)
            GLES20.glDeleteShader(vertexShader)
            GLES20.glDeleteShader(fragmentShader)
            throw RuntimeException("program link failed: $log")
        }

        GLES20.glDetachShader(prog, vertexShader)
        GLES20.glDetachShader(prog, fragmentShader)
        GLES20.glDeleteShader(vertexShader)
        GLES20.glDeleteShader(fragmentShader)

        val error = GLES20.glGetError()
        if (error != GLES20.GL_NO_ERROR) {
            Log.w(TAG, "GL error after program setup: 0x${Integer.toHexString(error)}")
        }
        return prog
    }

    private fun compileShader(type: Int, source: String): Int {
        val shader = GLES20.glCreateShader(type)
        if (shader == 0) {
            throw RuntimeException("glCreateShader($type) returned 0")
        }
        GLES20.glShaderSource(shader, source)
        GLES20.glCompileShader(shader)

        val status = IntArray(1)
        GLES20.glGetShaderiv(shader, GLES20.GL_COMPILE_STATUS, status, 0)
        if (status[0] == 0) {
            val log = GLES20.glGetShaderInfoLog(shader)
            GLES20.glDeleteShader(shader)
            throw RuntimeException("shader compile failed ($type): $log")
        }
        return shader
    }

    // =====================================================================
    // growth helpers (only ever run when the arrays are too small)
    // =====================================================================

    private fun newVertexBuffer(floats: Int): FloatBuffer =
        ByteBuffer.allocateDirect(floats * BYTES_PER_FLOAT)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()

    private fun ensureVertexCapacity(verticesNeeded: Int) {
        val neededFloats = verticesNeeded * VERTEX_FLOATS
        if (vertices.capacity() >= neededFloats) {
            return
        }
        var capacity = vertices.capacity()
        while (capacity < neededFloats) {
            capacity *= 2
        }
        val bigger = newVertexBuffer(capacity)
        val old = vertices
        old.position(0)
        old.limit(vertexCount * VERTEX_FLOATS)
        bigger.put(old)
        old.limit(old.capacity())
        bigger.position(0)
        bigger.limit(bigger.capacity())
        vertices = bigger
        Log.i(TAG, "vertex buffer grown to $capacity floats")
    }

    private fun ensureBatchCapacity(needed: Int) {
        if (batchFirst.size >= needed) {
            return
        }
        var capacity = batchFirst.size
        while (capacity < needed) {
            capacity *= 2
        }
        batchFirst = batchFirst.copyOf(capacity)
        batchLength = batchLength.copyOf(capacity)
        batchTexture = batchTexture.copyOf(capacity)
        batchAdditive = batchAdditive.copyOf(capacity)
    }

    private fun ensureCommandCapacity(commands: Int) {
        val floats = commands * NativeCore.FLOATS_PER_CMD
        if (cmdFloats.size < floats) {
            cmdFloats = FloatArray(floats)
            Log.i(TAG, "command float array grown to $floats")
        }
        val ints = commands * NativeCore.INTS_PER_CMD
        if (cmdInts.size < ints) {
            cmdInts = IntArray(ints)
            Log.i(TAG, "command int array grown to $ints")
        }
    }

    private fun ensureEventCapacity(events: Int) {
        val floats = events * NativeCore.FLOATS_PER_EVENT
        if (eventFloats.size < floats) {
            eventFloats = FloatArray(floats)
        }
        if (eventInts.size < events * NativeCore.INTS_PER_EVENT) {
            eventInts = IntArray(events * NativeCore.INTS_PER_EVENT)
        }
    }

    private fun stateName(state: Int): String = when (state) {
        Int.MIN_VALUE -> "NONE"
        NativeCore.STATE_TITLE -> "TITLE"
        NativeCore.STATE_PLAYING -> "PLAYING"
        NativeCore.STATE_LEVEL_UP -> "LEVEL_UP"
        NativeCore.STATE_SHOP -> "SHOP"
        NativeCore.STATE_PAUSED -> "PAUSED"
        NativeCore.STATE_GAME_OVER -> "GAME_OVER"
        else -> "STATE($state)"
    }

    companion object {
        private const val TAG = "GameRenderer"

        // ---- vertex layout (kept in one place; mirrored by putVertex) ----
        private const val VERTEX_FLOATS = 8 // x, y, u, v, r, g, b, a
        private const val BYTES_PER_FLOAT = 4
        private const val VERTEX_STRIDE_BYTES = VERTEX_FLOATS * BYTES_PER_FLOAT
        private const val VERTICES_PER_QUAD = 6

        private const val ATTRIB_POSITION = 0
        private const val ATTRIB_UV = 1
        private const val ATTRIB_COLOR = 2

        /*
         * Initial capacities, grown on demand and never shrunk.
         *
         * Measured against the real core (host-selfcheck, 900 simulated frames):
         * the busiest frame produced 427 commands, and the largest vertex count
         * per frame is 2 quads (shadow + body) x 6 vertices x that many commands.
         * 8192 vertices = 1365 quads, i.e. roughly 3x the observed worst case, so
         * the steady state never reallocates; a genuinely bigger frame merely
         * grows the buffers once.
         */
        private const val INITIAL_VERTICES = 8192
        private const val INITIAL_BATCHES = 128
        private const val INITIAL_COMMANDS = 1024
        private const val INITIAL_EVENTS = 128

        /**
         * Hard ceiling on vertices per frame.  [MAX_VERTICES_PER_FRAME] /
         * [VERTICES_PER_QUAD] quads is far beyond anything the core emits; the
         * cap exists so a corrupt command stream cannot exhaust the heap.
         */
        private const val MAX_VERTICES_PER_FRAME = 1 shl 17 // 131072 vertices

        // ---- timing ------------------------------------------------------
        private const val MAX_DT_SECONDS = 0.05f // 50 ms; the core clamps too
        private const val AUTOSAVE_INTERVAL_NANOS = 5_000_000_000L // 5 s
        private const val STATUS_POLL_FRAMES = 60

        // ---- save blob ---------------------------------------------------
        private const val SAVE_INITIAL_BYTES = 1024
        private const val SAVE_MAX_BYTES = 1 shl 20 // 1 MiB

        // ---- shadow ------------------------------------------------------
        private const val SHADOW_OFFSET_VIRTUAL = 1.5f
        private const val SHADOW_ALPHA_SCALE = 0.45f

        // ---- shell overlay ----------------------------------------------
        private const val DRAW_TOUCH_OVERLAY = true
        private const val AIM_MARKER_VIRTUAL = 10f
        private val COS_45 = cos((Math.PI / 4.0)).toFloat()
        private val SIN_45 = sin((Math.PI / 4.0)).toFloat()

        /**
         * Vertex shader.
         *
         * `uScale` is `gc_view_scale` on both axes: virtual units and pixels
         * share origin and orientation, so the mapping is a pure scale with no
         * translation (no letterbox, no offset).  The remaining work is the
         * pixel -> normalised-device-coordinate step and the y flip, because the
         * ABI is y-down and GL is y-up.
         */
        private val VERTEX_SHADER_SOURCE = """
            uniform vec2 uScale;
            uniform vec2 uViewport;
            attribute vec2 aPos;
            attribute vec2 aUV;
            attribute vec4 aColor;
            varying vec2 vUV;
            varying vec4 vColor;
            void main() {
                vec2 pixel = aPos * uScale;
                vec2 ndc = vec2(
                    (pixel.x / uViewport.x) * 2.0 - 1.0,
                    1.0 - (pixel.y / uViewport.y) * 2.0
                );
                gl_Position = vec4(ndc, 0.0, 1.0);
                vUV = aUV;
                vColor = aColor;
            }
        """.trimIndent()

        /**
         * Fragment shader: straight (non-premultiplied) alpha in, straight alpha
         * out, because both blend modes the renderer selects
         * (`GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA` and `GL_SRC_ALPHA, GL_ONE`)
         * consume non-premultiplied colour.
         */
        private val FRAGMENT_SHADER_SOURCE = """
            precision mediump float;
            uniform sampler2D uTexture;
            uniform int uUseTexture;
            varying vec2 vUV;
            varying vec4 vColor;
            void main() {
                vec4 color = vColor;
                if (uUseTexture == 1) {
                    color *= texture2D(uTexture, vUV);
                }
                gl_FragColor = color;
            }
        """.trimIndent()
    }
}
