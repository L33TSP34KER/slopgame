/*
 * game_jni.c -- the *entire* Android<=>core seam.
 *
 * This file is deliberately dumb: it owns no game state, does no maths, keeps no
 * globals and makes no policy decisions.  Every function is a straight
 * forwarding shim between the Kotlin renderer (package com.gamecore,
 * class/object NativeCore) and the frozen C ABI in <game_core.h>.
 *
 * THREAD AFFINITY
 * ---------------
 * The header says every entry point is thread-affine to the thread that called
 * gc_create().  The Kotlin side therefore creates the handle *and* performs
 * every subsequent call on the GLSurfaceView GL thread.  This wrapper adds no
 * locking of its own (that would be a lie: the core is not thread safe).
 *
 * HANDLE MARSHALLING
 * ------------------
 * The opaque gc_handle* travels to Kotlin as a jlong.  Kotlin stores it as a
 * Long and can do nothing with it except hand it back; no pointer arithmetic,
 * no dereference, no way to construct a valid one accidentally.
 *
 * ARRAY PACKING (mirrored by Kotlin NativeCore constants -- keep in sync!)
 * ----------------------------------------------------------------------
 * nativeFillCommands(handle, count, floats, ints) writes `count` (clamped to
 * both array capacities) commands as fixed-stride SoA:
 *
 *   floats[i * 9 + 0] = x        (virtual units, CENTER of the quad)
 *   floats[i * 9 + 1] = y        (virtual units, CENTER of the quad)
 *   floats[i * 9 + 2] = w        (virtual units)
 *   floats[i * 9 + 3] = h        (virtual units)
 *   floats[i * 9 + 4] = rot      (clockwise radians about (x,y))
 *   floats[i * 9 + 5] = u0       (atlas UV rect, GC_CMD_GLYPH only)
 *   floats[i * 9 + 6] = v0
 *   floats[i * 9 + 7] = u1
 *   floats[i * 9 + 8] = v1
 *
 *   ints[i * 4 + 0] = kind       (gc_cmd_kind: 1 sprite, 2 rect, 3 glyph)
 *   ints[i * 4 + 1] = sprite     (gc_sprite_id, GC_CMD_SPRITE only)
 *   ints[i * 4 + 2] = rgba       (0xAARRGGBB straight alpha, bit pattern as
 *                                 signed jint -- Kotlin masks with ushr/and)
 *   ints[i * 4 + 3] = flags      (GC_FLAG_*)
 *
 * nativeFillEvents(handle, count, floats, ints):
 *   floats[i * 3 + 0] = x
 *   floats[i * 3 + 1] = y
 *   floats[i * 3 + 2] = value
 *   ints[i * 1 + 0]   = type     (gc_event_type)
 *
 * Both fill functions return the number of records actually written, which is
 * min(count, gc_*() count, capacity of floats, capacity of ints).
 *
 * NO PER-FRAME JAVA ALLOCATION
 * ----------------------------
 * The hot paths (FillCommands / FillEvents / Status) use
 * GetPrimitiveArrayCritical so the VM pins (or, at worst, copies once) the
 * caller's long-lived arrays instead of allocating a fresh copy per call.  The
 * critical section contains nothing but a memcpy from the core's own flat array
 * -- no JNI calls, no blocking, no allocation -- which is exactly the
 * sanctioned use of a critical region.  The cold paths (save/load, string
 * names) use the ordinary Get<Type>ArrayElements.
 */
#include <jni.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <android/log.h>

#include "game_core.h"

#define LOG_TAG "GameJNI"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

/* ------------------------------------------------------------------ */
/* Compile-time proof that our packing matches the header exactly.     */
/* ------------------------------------------------------------------ */

/* C89-compatible static assert: a negative array size is a hard error. */
#define GC_GLUE_(a, b) a##b
#define GC_GLUE(a, b) GC_GLUE_(a, b)
#define GC_ASSERT_LAYOUT(cond, tag) \
    typedef char GC_GLUE(gc_layout_assert_, tag)[(cond) ? 1 : -1]

/*
 * Expected gc_cmd byte layout on every ABI we ship (all members are 4-byte
 * aligned, so ILP32 and LP64 agree):
 *
 *   offset  size  field
 *        0     4  int32_t  kind
 *        4     4  int32_t  sprite
 *        8     4  float    x
 *       12     4  float    y
 *       16     4  float    w
 *       20     4  float    h
 *       24     4  float    rot
 *       28     4  uint32_t rgba
 *       32     4  float    u0
 *       36     4  float    v0
 *       40     4  float    u1
 *       44     4  float    v1
 *       48     4  int32_t  flags
 *       52     4  int32_t  _pad
 *      ----  ----
 *   sizeof = 56, alignof = 4 (56 is also a multiple of 8)
 */
GC_ASSERT_LAYOUT(sizeof(gc_cmd) == 56, gc_cmd_size_is_56);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, kind) == 0, gc_cmd_kind_at_0);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, sprite) == 4, gc_cmd_sprite_at_4);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, x) == 8, gc_cmd_x_at_8);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, y) == 12, gc_cmd_y_at_12);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, w) == 16, gc_cmd_w_at_16);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, h) == 20, gc_cmd_h_at_20);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, rot) == 24, gc_cmd_rot_at_24);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, rgba) == 28, gc_cmd_rgba_at_28);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, u0) == 32, gc_cmd_u0_at_32);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, v0) == 36, gc_cmd_v0_at_36);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, u1) == 40, gc_cmd_u1_at_40);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, v1) == 44, gc_cmd_v1_at_44);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, flags) == 48, gc_cmd_flags_at_48);
GC_ASSERT_LAYOUT(offsetof(gc_cmd, _pad) == 52, gc_cmd_pad_at_52);

/* gc_event: int32 type @0, float x@4, y@8, value@12 -> 16 bytes. */
GC_ASSERT_LAYOUT(sizeof(gc_event) == 16, gc_event_size_is_16);
GC_ASSERT_LAYOUT(offsetof(gc_event, type) == 0, gc_event_type_at_0);
GC_ASSERT_LAYOUT(offsetof(gc_event, x) == 4, gc_event_x_at_4);
GC_ASSERT_LAYOUT(offsetof(gc_event, y) == 8, gc_event_y_at_8);
GC_ASSERT_LAYOUT(offsetof(gc_event, value) == 12, gc_event_value_at_12);

/* gc_status: 7 * int32 then 3 * float -> 40 bytes. */
GC_ASSERT_LAYOUT(sizeof(gc_status) == 40, gc_status_size_is_40);
GC_ASSERT_LAYOUT(offsetof(gc_status, wave) == 0, gc_status_wave_at_0);
GC_ASSERT_LAYOUT(offsetof(gc_status, level) == 4, gc_status_level_at_4);
GC_ASSERT_LAYOUT(offsetof(gc_status, kills) == 8, gc_status_kills_at_8);
GC_ASSERT_LAYOUT(offsetof(gc_status, money) == 12, gc_status_money_at_12);
GC_ASSERT_LAYOUT(offsetof(gc_status, score) == 16, gc_status_score_at_16);
GC_ASSERT_LAYOUT(offsetof(gc_status, best_score) == 20, gc_status_best_at_20);
GC_ASSERT_LAYOUT(offsetof(gc_status, state) == 24, gc_status_state_at_24);
GC_ASSERT_LAYOUT(offsetof(gc_status, player_hp) == 28, gc_status_hp_at_28);
GC_ASSERT_LAYOUT(offsetof(gc_status, player_hp_max) == 32, gc_status_hpmax_at_32);
GC_ASSERT_LAYOUT(offsetof(gc_status, time_alive) == 36, gc_status_time_at_36);

/* gc_input: 4 * float then 3 * int32 -> 28 bytes. */
GC_ASSERT_LAYOUT(sizeof(gc_input) == 28, gc_input_size_is_28);
GC_ASSERT_LAYOUT(offsetof(gc_input, move_x) == 0, gc_input_movx_at_0);
GC_ASSERT_LAYOUT(offsetof(gc_input, move_y) == 4, gc_input_movy_at_4);
GC_ASSERT_LAYOUT(offsetof(gc_input, aim_x) == 8, gc_input_aimx_at_8);
GC_ASSERT_LAYOUT(offsetof(gc_input, aim_y) == 12, gc_input_aimy_at_12);
GC_ASSERT_LAYOUT(offsetof(gc_input, pointer_active) == 16, gc_input_pact_at_16);
GC_ASSERT_LAYOUT(offsetof(gc_input, pointer_down) == 20, gc_input_pdown_at_20);
GC_ASSERT_LAYOUT(offsetof(gc_input, buttons) == 24, gc_input_buttons_at_24);

/* ------------------------------------------------------------------ */
/* Packing strides (mirrored in Kotlin: NativeCore.FLOATS_PER_CMD, ...) */
/* ------------------------------------------------------------------ */
#define GC_CMD_FLOATS   9
#define GC_CMD_INTS     4
#define GC_EVT_FLOATS   3
#define GC_EVT_INTS     1
#define GC_STATUS_INTS  7
#define GC_STATUS_FLOATS 3

static inline gc_handle *gc_unwrap(jlong handle)
{
    return (gc_handle *)(intptr_t)handle;
}

static inline jlong gc_wrap(gc_handle *h)
{
    return (jlong)(intptr_t)h;
}

/* ------------------------------------------------------------------ */
/* version / lifecycle                                                */
/* ------------------------------------------------------------------ */

JNIEXPORT jint JNICALL
Java_com_gamecore_NativeCore_nativeAbiVersion(JNIEnv *env, jobject thiz)
{
    (void)env; (void)thiz;
    return (jint)gc_abi_version();
}

/*
 * Returns 0 on failure (NULL is an invalid handle everywhere in this file).
 * Refuses to create a run when the loaded core disagrees with the header the
 * wrapper was compiled against.
 */
JNIEXPORT jlong JNICALL
Java_com_gamecore_NativeCore_nativeCreate(JNIEnv *env, jobject thiz, jint seed)
{
    (void)env; (void)thiz;

    uint32_t abi = gc_abi_version();
    if (abi != GC_ABI_VERSION) {
        LOGE("ABI mismatch: libgame_core=%u, header=%u -- refusing to create",
             (unsigned)abi, (unsigned)GC_ABI_VERSION);
        return 0;
    }
    gc_handle *h = gc_create((uint32_t)seed);
    if (h == NULL) {
        LOGE("gc_create(NULL) -- out of memory?");
        return 0;
    }
    LOGI("gc_create(seed=%d) -> handle %p", (int)seed, (void *)h);
    return gc_wrap(h);
}

JNIEXPORT void JNICALL
Java_com_gamecore_NativeCore_nativeDestroy(JNIEnv *env, jobject thiz, jlong handle)
{
    (void)env; (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL) {
        return;
    }
    LOGI("gc_destroy(%p)", (void *)h);
    gc_destroy(h); /* NULL is ignored by the core; 0 is not a valid handle here anyway */
}

/* ------------------------------------------------------------------ */
/* framebuffer geometry                                               */
/* ------------------------------------------------------------------ */

JNIEXPORT void JNICALL
Java_com_gamecore_NativeCore_nativeResize(JNIEnv *env, jobject thiz, jlong handle,
                                          jint fbWidth, jint fbHeight,
                                          jfloat safeLeft, jfloat safeTop,
                                          jfloat safeRight, jfloat safeBottom)
{
    (void)env; (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL) {
        return;
    }
    if (fbWidth < 0) fbWidth = 0;
    if (fbHeight < 0) fbHeight = 0;
    gc_resize(h, (int32_t)fbWidth, (int32_t)fbHeight,
              safeLeft, safeTop, safeRight, safeBottom);
}

/*
 * pixels per virtual unit, straight from gc_view_scale().  The renderer uses it
 * both as a vertex scale and as the divisor that mirrors gc_pixels_to_virtual().
 * Returns 1.0f for a null handle so touch maths can never divide by zero.
 */
JNIEXPORT jfloat JNICALL
Java_com_gamecore_NativeCore_nativeViewScale(JNIEnv *env, jobject thiz, jlong handle)
{
    (void)env; (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL) {
        return 1.0f;
    }
    float s = gc_view_scale(h);
    return (s > 0.0f) ? (jfloat)s : 1.0f;
}

/* ------------------------------------------------------------------ */
/* simulation step                                                    */
/* ------------------------------------------------------------------ */

/*
 * Parameter order mirrors the gc_input struct field order exactly:
 *   move_x, move_y, aim_x, aim_y, pointer_active, pointer_down, buttons
 * dt is in seconds.  The core clamps it internally.
 */
JNIEXPORT void JNICALL
Java_com_gamecore_NativeCore_nativeUpdate(JNIEnv *env, jobject thiz, jlong handle,
                                          jfloat dt,
                                          jfloat moveX, jfloat moveY,
                                          jfloat aimX, jfloat aimY,
                                          jint pointerActive, jint pointerDown,
                                          jint buttons)
{
    (void)env; (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL) {
        return;
    }
    /* Zero-initialised so padding / future fields can never be garbage. */
    gc_input in;
    memset(&in, 0, sizeof(in));
    in.move_x         = moveX;
    in.move_y         = moveY;
    in.aim_x          = aimX;
    in.aim_y          = aimY;
    in.pointer_active = pointerActive;
    in.pointer_down   = pointerDown;
    in.buttons        = (uint32_t)buttons;
    gc_update(h, &in, dt);
}

/* ------------------------------------------------------------------ */
/* draw commands                                                      */
/* ------------------------------------------------------------------ */

JNIEXPORT jint JNICALL
Java_com_gamecore_NativeCore_nativeCmdCount(JNIEnv *env, jobject thiz, jlong handle)
{
    (void)env; (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL) {
        return 0;
    }
    int32_t n = 0;
    const gc_cmd *cmds = gc_cmds(h, &n);
    if (cmds == NULL || n < 0) {
        return 0;
    }
    return (jint)n;
}

/*
 * See the file header for the exact packing.  Returns the number of commands
 * written; never writes past either array.
 */
JNIEXPORT jint JNICALL
Java_com_gamecore_NativeCore_nativeFillCommands(JNIEnv *env, jobject thiz, jlong handle,
                                                jint count,
                                                jfloatArray floats, jintArray ints)
{
    (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL || count <= 0 || floats == NULL || ints == NULL) {
        return 0;
    }

    int32_t available = 0;
    const gc_cmd *cmds = gc_cmds(h, &available);
    if (cmds == NULL || available <= 0) {
        return 0;
    }

    /* Lengths must be read *before* entering a critical section. */
    const jsize floatLen = (*env)->GetArrayLength(env, floats);
    const jsize intLen   = (*env)->GetArrayLength(env, ints);

    int32_t capacity = (int32_t)(floatLen / GC_CMD_FLOATS);
    if ((int32_t)(intLen / GC_CMD_INTS) < capacity) {
        capacity = (int32_t)(intLen / GC_CMD_INTS);
    }
    if (capacity <= 0) {
        return 0;
    }

    int32_t n = available;
    if (n > count) {
        n = count;
    }
    if (n > capacity) {
        n = capacity;
    }

    jfloat *f = (jfloat *)(*env)->GetPrimitiveArrayCritical(env, floats, NULL);
    if (f == NULL) {
        return 0;
    }
    jint *iv = (jint *)(*env)->GetPrimitiveArrayCritical(env, ints, NULL);
    if (iv == NULL) {
        (*env)->ReleasePrimitiveArrayCritical(env, floats, f, JNI_ABORT);
        return 0;
    }

    for (int32_t i = 0; i < n; ++i) {
        const gc_cmd *c = &cmds[i];
        jfloat *fp = f + (size_t)i * GC_CMD_FLOATS;
        jint   *ip = iv + (size_t)i * GC_CMD_INTS;

        fp[0] = (jfloat)c->x;
        fp[1] = (jfloat)c->y;
        fp[2] = (jfloat)c->w;
        fp[3] = (jfloat)c->h;
        fp[4] = (jfloat)c->rot;
        fp[5] = (jfloat)c->u0;
        fp[6] = (jfloat)c->v0;
        fp[7] = (jfloat)c->u1;
        fp[8] = (jfloat)c->v1;

        ip[0] = (jint)c->kind;
        ip[1] = (jint)c->sprite;
        ip[2] = (jint)c->rgba; /* 0xAARRGGBB bit pattern, sign is irrelevant */
        ip[3] = (jint)c->flags;
    }

    (*env)->ReleasePrimitiveArrayCritical(env, ints, iv, 0);
    (*env)->ReleasePrimitiveArrayCritical(env, floats, f, 0);
    return (jint)n;
}

/* ------------------------------------------------------------------ */
/* events (audio / haptics)                                           */
/* ------------------------------------------------------------------ */

JNIEXPORT jint JNICALL
Java_com_gamecore_NativeCore_nativeEventCount(JNIEnv *env, jobject thiz, jlong handle)
{
    (void)env; (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL) {
        return 0;
    }
    int32_t n = 0;
    const gc_event *ev = gc_events(h, &n);
    if (ev == NULL || n < 0) {
        return 0;
    }
    return (jint)n;
}

JNIEXPORT jint JNICALL
Java_com_gamecore_NativeCore_nativeFillEvents(JNIEnv *env, jobject thiz, jlong handle,
                                              jint count,
                                              jfloatArray floats, jintArray ints)
{
    (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL || count <= 0 || floats == NULL || ints == NULL) {
        return 0;
    }

    int32_t available = 0;
    const gc_event *events = gc_events(h, &available);
    if (events == NULL || available <= 0) {
        return 0;
    }

    const jsize floatLen = (*env)->GetArrayLength(env, floats);
    const jsize intLen   = (*env)->GetArrayLength(env, ints);

    int32_t capacity = (int32_t)(floatLen / GC_EVT_FLOATS);
    if ((int32_t)(intLen / GC_EVT_INTS) < capacity) {
        capacity = (int32_t)(intLen / GC_EVT_INTS);
    }
    if (capacity <= 0) {
        return 0;
    }

    int32_t n = available;
    if (n > count) {
        n = count;
    }
    if (n > capacity) {
        n = capacity;
    }

    jfloat *f = (jfloat *)(*env)->GetPrimitiveArrayCritical(env, floats, NULL);
    if (f == NULL) {
        return 0;
    }
    jint *iv = (jint *)(*env)->GetPrimitiveArrayCritical(env, ints, NULL);
    if (iv == NULL) {
        (*env)->ReleasePrimitiveArrayCritical(env, floats, f, JNI_ABORT);
        return 0;
    }

    for (int32_t i = 0; i < n; ++i) {
        const gc_event *e = &events[i];
        jfloat *fp = f + (size_t)i * GC_EVT_FLOATS;
        jint   *ip = iv + (size_t)i * GC_EVT_INTS;

        fp[0] = (jfloat)e->x;
        fp[1] = (jfloat)e->y;
        fp[2] = (jfloat)e->value;
        ip[0] = (jint)e->type;
    }

    (*env)->ReleasePrimitiveArrayCritical(env, ints, iv, 0);
    (*env)->ReleasePrimitiveArrayCritical(env, floats, f, 0);
    return (jint)n;
}

/* ------------------------------------------------------------------ */
/* status snapshot                                                    */
/* ------------------------------------------------------------------ */

/*
 * ints  [0..6] = wave, level, kills, money, score, best_score, state
 * floats[0..2] = player_hp, player_hp_max, time_alive
 * Returns 1 when the snapshot was written, 0 otherwise.
 */
JNIEXPORT jint JNICALL
Java_com_gamecore_NativeCore_nativeStatus(JNIEnv *env, jobject thiz, jlong handle,
                                          jintArray ints, jfloatArray floats)
{
    (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL || ints == NULL || floats == NULL) {
        return 0;
    }
    if ((*env)->GetArrayLength(env, ints) < GC_STATUS_INTS ||
        (*env)->GetArrayLength(env, floats) < GC_STATUS_FLOATS) {
        LOGE("nativeStatus: arrays too small (need %d ints / %d floats)",
             GC_STATUS_INTS, GC_STATUS_FLOATS);
        return 0;
    }

    gc_status st;
    memset(&st, 0, sizeof(st));
    gc_status_get(h, &st);

    jint *iv = (jint *)(*env)->GetPrimitiveArrayCritical(env, ints, NULL);
    if (iv == NULL) {
        return 0;
    }
    jfloat *fv = (jfloat *)(*env)->GetPrimitiveArrayCritical(env, floats, NULL);
    if (fv == NULL) {
        (*env)->ReleasePrimitiveArrayCritical(env, ints, iv, JNI_ABORT);
        return 0;
    }

    iv[0] = (jint)st.wave;
    iv[1] = (jint)st.level;
    iv[2] = (jint)st.kills;
    iv[3] = (jint)st.money;
    iv[4] = (jint)st.score;
    iv[5] = (jint)st.best_score;
    iv[6] = (jint)st.state;

    fv[0] = (jfloat)st.player_hp;
    fv[1] = (jfloat)st.player_hp_max;
    fv[2] = (jfloat)st.time_alive;

    (*env)->ReleasePrimitiveArrayCritical(env, floats, fv, 0);
    (*env)->ReleasePrimitiveArrayCritical(env, ints, iv, 0);
    return 1;
}

/* ------------------------------------------------------------------ */
/* save / load (opaque blob, stored in SharedPreferences by Kotlin)    */
/* ------------------------------------------------------------------ */

/*
 * Returns the number of bytes written, or -1 when the blob does not fit in
 * `capacity` (Kotlin then retries with a bigger array) or cannot be produced.
 */
JNIEXPORT jint JNICALL
Java_com_gamecore_NativeCore_nativeSave(JNIEnv *env, jobject thiz, jlong handle,
                                        jbyteArray out, jint capacity)
{
    (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL || out == NULL) {
        return -1;
    }
    const jsize len = (*env)->GetArrayLength(env, out);
    if (len <= 0) {
        return -1;
    }
    jint use = capacity;
    if (use <= 0 || use > len) {
        use = len;
    }

    jbyte *buf = (*env)->GetByteArrayElements(env, out, NULL);
    if (buf == NULL) {
        return -1;
    }
    /* cap must be > 0 for gc_save to write anything at all. */
    int32_t written = gc_save(h, buf, (int32_t)use);
    (*env)->ReleaseByteArrayElements(env, out, buf, (written >= 0) ? 0 : JNI_ABORT);
    return (jint)written;
}

JNIEXPORT jint JNICALL
Java_com_gamecore_NativeCore_nativeLoad(JNIEnv *env, jobject thiz, jlong handle,
                                        jbyteArray data, jint length)
{
    (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL || data == NULL) {
        return -1;
    }
    const jsize len = (*env)->GetArrayLength(env, data);
    if (len <= 0) {
        return -1;
    }
    jint use = length;
    if (use <= 0 || use > len) {
        use = len;
    }

    jbyte *buf = (*env)->GetByteArrayElements(env, data, NULL);
    if (buf == NULL) {
        return -1;
    }
    int32_t rc = gc_load(h, buf, (int32_t)use);
    (*env)->ReleaseByteArrayElements(env, data, buf, JNI_ABORT); /* read-only */
    return (jint)rc;
}

/* ------------------------------------------------------------------ */
/* debug / tooling hook (never used by the shipping render path)       */
/* ------------------------------------------------------------------ */

JNIEXPORT void JNICALL
Java_com_gamecore_NativeCore_nativeDebug(JNIEnv *env, jobject thiz, jlong handle,
                                         jint cmd, jfloat value)
{
    (void)env; (void)thiz;
    gc_handle *h = gc_unwrap(handle);
    if (h == NULL) {
        return;
    }
    gc_debug(h, (int32_t)cmd, value);
}

/* ------------------------------------------------------------------ */
/* asset names                                                        */
/* ------------------------------------------------------------------ */

/*
 * Returns GC_SPR_COUNT + 1 strings:
 *   [0 .. GC_SPR_COUNT-1] = gc_sprite_file(i)   (may be null in theory)
 *   [GC_SPR_COUNT]        = gc_font_atlas() file name (may be null)
 *
 * Called once per EGL surface creation, never per frame, so the one-off string
 * allocation is irrelevant.
 */
JNIEXPORT jobjectArray JNICALL
Java_com_gamecore_NativeCore_nativeAssetNames(JNIEnv *env, jobject thiz)
{
    (void)thiz;

    const jsize spriteCount = (jsize)GC_SPR_COUNT;
    const jsize total = spriteCount + 1;

    jclass stringClass = (*env)->FindClass(env, "java/lang/String");
    if (stringClass == NULL) {
        return NULL;
    }
    jobjectArray array = (*env)->NewObjectArray(env, total, stringClass, NULL);
    if (array == NULL) {
        return NULL;
    }

    for (jsize i = 0; i < spriteCount; ++i) {
        const char *name = gc_sprite_file((int32_t)i);
        jstring s = (name != NULL) ? (*env)->NewStringUTF(env, name) : NULL;
        /* SetObjectArrayElement with a NULL value stores a null element. */
        (*env)->SetObjectArrayElement(env, array, i, s);
        if (s != NULL) {
            (*env)->DeleteLocalRef(env, s);
        }
    }

    const char *atlasFile = NULL;
    int32_t atlasW = 0;
    int32_t atlasH = 0;
    gc_font_atlas(&atlasFile, &atlasW, &atlasH);
    jstring atlas = (atlasFile != NULL) ? (*env)->NewStringUTF(env, atlasFile) : NULL;
    (*env)->SetObjectArrayElement(env, array, spriteCount, atlas);
    if (atlas != NULL) {
        (*env)->DeleteLocalRef(env, atlas);
    }
    LOGI("assets: %d sprites + atlas '%s' (%dx%d)",
         (int)spriteCount, (atlasFile != NULL) ? atlasFile : "<none>",
         (int)atlasW, (int)atlasH);

    return array;
}
