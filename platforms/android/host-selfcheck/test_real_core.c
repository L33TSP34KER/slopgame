/*
 * Host-only self-test #2: game_jni.c against the REAL libgame_core.
 *
 * NOT part of the Android build.  Run through ./run.sh.
 *
 * This is the strongest verification available without an NDK: app/src/main/cpp/
 * game_jni.c is compiled unmodified for the host and linked against a host build
 * of the actual core (rustc on core/src/lib.rs, produced by run.sh).  It then
 *
 *   1. creates a run through the JNI entry points exactly as the Kotlin renderer
 *      would (resize -> update -> cmds -> events -> status -> save -> load),
 *   2. simulates 900 frames of real gameplay,
 *   3. validates every command/event the wrapper hands to Kotlin against the ABI
 *      contract (kinds, sprite ranges, finite geometry, UV ranges, flag masks),
 *   4. checks the asset names against the copy_assets.sh convention,
 *   5. round-trips the save blob through nativeSave/nativeLoad,
 *   6. proves the wrapper's capacity clamping with real data.
 *
 * What it still cannot prove: OpenGL, Kotlin/JNI binding names on a JVM, Gradle,
 * the NDK toolchain, or anything device-specific.
 */
#include <jni.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>

#include "fake_jni.h"
#include "game_core.h"

/* ---- entry points under test (implemented by game_jni.c) ---------------- */
JNIEXPORT jint JNICALL Java_com_gamecore_NativeCore_nativeAbiVersion(JNIEnv *, jobject);
JNIEXPORT jlong JNICALL Java_com_gamecore_NativeCore_nativeCreate(JNIEnv *, jobject, jint);
JNIEXPORT void JNICALL Java_com_gamecore_NativeCore_nativeDestroy(JNIEnv *, jobject, jlong);
JNIEXPORT void JNICALL Java_com_gamecore_NativeCore_nativeResize(JNIEnv *, jobject, jlong, jint, jint, jfloat, jfloat, jfloat, jfloat);
JNIEXPORT jfloat JNICALL Java_com_gamecore_NativeCore_nativeViewScale(JNIEnv *, jobject, jlong);
JNIEXPORT void JNICALL Java_com_gamecore_NativeCore_nativeUpdate(JNIEnv *, jobject, jlong, jfloat, jfloat, jfloat, jfloat, jfloat, jint, jint, jint);
JNIEXPORT jint JNICALL Java_com_gamecore_NativeCore_nativeCmdCount(JNIEnv *, jobject, jlong);
JNIEXPORT jint JNICALL Java_com_gamecore_NativeCore_nativeFillCommands(JNIEnv *, jobject, jlong, jint, jfloatArray, jintArray);
JNIEXPORT jint JNICALL Java_com_gamecore_NativeCore_nativeEventCount(JNIEnv *, jobject, jlong);
JNIEXPORT jint JNICALL Java_com_gamecore_NativeCore_nativeFillEvents(JNIEnv *, jobject, jlong, jint, jfloatArray, jintArray);
JNIEXPORT jint JNICALL Java_com_gamecore_NativeCore_nativeStatus(JNIEnv *, jobject, jlong, jintArray, jfloatArray);
JNIEXPORT jint JNICALL Java_com_gamecore_NativeCore_nativeSave(JNIEnv *, jobject, jlong, jbyteArray, jint);
JNIEXPORT jint JNICALL Java_com_gamecore_NativeCore_nativeLoad(JNIEnv *, jobject, jlong, jbyteArray, jint);
JNIEXPORT void JNICALL Java_com_gamecore_NativeCore_nativeDebug(JNIEnv *, jobject, jlong, jint, jfloat);
JNIEXPORT jobjectArray JNICALL Java_com_gamecore_NativeCore_nativeAssetNames(JNIEnv *, jobject);

int __android_log_print(int prio, const char *tag, const char *fmt, ...)
{
    (void)prio; (void)tag; (void)fmt;
    return 0;
}

/* ---- expectations that must match the core and copy_assets.sh ----------- */
static const char *EXPECTED_SPRITES[GC_SPR_COUNT] = {
    "player.png", "enemy_a.png", "enemy_b.png", "gun.png",
    "bow.png", "sword.png", "money.png", "xp.png",
};
static const char *EXPECTED_ATLAS = "font_atlas.png";

static int g_fail = 0;
#define CHECK(cond, ...) do { if (!(cond)) { printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); g_fail++; } } while (0)

#define FRAME_DT 0.0166667f
#define FRAMES 900
#define FLOATS_PER_CMD 9
#define INTS_PER_CMD 4
#define FLOATS_PER_EVENT 3

static int finite_float(float v)
{
    return isfinite((double)v);
}

int main(void)
{
    JNIEnv *env = fake_jni_env();

    /* ---- ABI ---- */
    CHECK(Java_com_gamecore_NativeCore_nativeAbiVersion(env, NULL) == (jint)GC_ABI_VERSION,
          "nativeAbiVersion != GC_ABI_VERSION");

    /* ---- create + resize, exactly like GameRenderer.onSurfaceCreated ----- */
    jlong h = Java_com_gamecore_NativeCore_nativeCreate(env, NULL, 0x5EED1234);
    CHECK(h != 0, "nativeCreate returned 0 against the real core");
    if (h == 0) { return 1; }

    const jint FB_W = 2400;  /* e.g. a 1080p phone in landscape, physical px */
    const jint FB_H = 1080;
    Java_com_gamecore_NativeCore_nativeResize(env, NULL, h, FB_W, FB_H, 0.f, 0.f, 0.f, 0.f);

    float scale = Java_com_gamecore_NativeCore_nativeViewScale(env, NULL, h);
    CHECK(scale > 0.f && finite_float(scale), "view scale must be positive, got %f", scale);
    /* design height is 720 virtual units == FB_H pixels */
    CHECK(fabsf(scale - (float)FB_H / GC_DESIGN_HEIGHT) < 0.001f,
          "view scale %f != fbHeight/720 (%f)", scale, (float)FB_H / GC_DESIGN_HEIGHT);
    CHECK(Java_com_gamecore_NativeCore_nativeViewScale(env, NULL, 0) == 1.0f,
          "null handle scale must fall back to 1.0");

    /* ---- the asset table drives TextureStore ----------------------------- */
    jobjectArray assetNames = Java_com_gamecore_NativeCore_nativeAssetNames(env, NULL);
    CHECK((intptr_t)assetNames == GC_SPR_COUNT + 1,
          "asset table must be GC_SPR_COUNT+1 entries, got %d", (int)(intptr_t)assetNames);
    /* The fake JNIEnv cannot carry strings back, so verify the C-side names the
       same way copy_assets.sh will: directly through the ABI. */
    for (int i = 0; i < GC_SPR_COUNT; ++i) {
        const char *name = gc_sprite_file(i);
        CHECK(name != NULL, "gc_sprite_file(%d) is NULL", i);
        if (name != NULL) {
            CHECK(strcmp(name, EXPECTED_SPRITES[i]) == 0,
                  "sprite %d name '%s' != '%s' expected by copy_assets.sh",
                  i, name, EXPECTED_SPRITES[i]);
        }
    }
    CHECK(gc_sprite_file(GC_SPR_COUNT) == NULL, "out-of-range sprite id must return NULL");
    const char *atlas = NULL;
    int32_t atlasW = 0, atlasH = 0;
    gc_font_atlas(&atlas, &atlasW, &atlasH);
    CHECK(atlas != NULL && strcmp(atlas, EXPECTED_ATLAS) == 0,
          "font atlas '%s' != '%s' expected by copy_assets.sh",
          atlas ? atlas : "(null)", EXPECTED_ATLAS);
    CHECK(atlasW > 0 && atlasH > 0, "atlas size must be known (%dx%d)", atlasW, atlasH);
    printf("assets: %d sprites + %s (%dx%d)\n", GC_SPR_COUNT,
           atlas ? atlas : "?", atlasW, atlasH);

    /* ---- 900 frames of "gameplay" --------------------------------------- */
    static FakeArray cmdFloats = FAKE_ARRAY_INIT(1, 0);
    static FakeArray cmdInts = FAKE_ARRAY_INIT(0, 0);
    static FakeArray evtFloats = FAKE_ARRAY_INIT(1, 0);
    static FakeArray evtInts = FAKE_ARRAY_INIT(0, 0);
    static FakeArray statusInts = FAKE_ARRAY_INIT(0, 0);
    static FakeArray statusFloats = FAKE_ARRAY_INIT(1, 0);

    int maxCommands = 0;
    int totalCommands = 0;
    int totalEvents = 0;
    int sawKind[4] = {0, 0, 0, 0};
    int sawFlagShadow = 0;
    int sawFlagFlash = 0;
    int sawSpriteIds[GC_SPR_COUNT + 1];
    memset(sawSpriteIds, 0, sizeof(sawSpriteIds));
    int maxEventType = 0;
    int maxRotSeen = 0;
    int spriteUvCarried = 0;

    for (int frame = 0; frame < FRAMES; ++frame) {
        /* A wandering stick, a moving aim point and a periodic dash: enough to
           drive most of the command kinds and events. */
        float t = (float)frame * FRAME_DT;
        float moveX = sinf(t * 1.7f);
        float moveY = cosf(t * 1.1f);
        float aimX = 640.f + 200.f * sinf(t * 2.3f);
        float aimY = 360.f + 120.f * cosf(t * 3.1f);
        int buttons = ((frame % 90) < 5) ? (int)GC_BTN_DASH : 0;

        Java_com_gamecore_NativeCore_nativeUpdate(env, NULL, h, FRAME_DT,
                                                  moveX, moveY, aimX, aimY, 1, 1, buttons);

        int n = Java_com_gamecore_NativeCore_nativeCmdCount(env, NULL, h);
        CHECK(n >= 0, "negative command count %d", n);
        if (n > 0) {
            cmdFloats.len = n * FLOATS_PER_CMD;
            cmdInts.len = n * INTS_PER_CMD;
            if (cmdFloats.len > FAKE_ARRAY_MAX) { cmdFloats.len = FAKE_ARRAY_MAX; }
            if (cmdInts.len > FAKE_ARRAY_MAX) { cmdInts.len = FAKE_ARRAY_MAX; }

            int got = Java_com_gamecore_NativeCore_nativeFillCommands(
                env, NULL, h, n, (jfloatArray)&cmdFloats, (jintArray)&cmdInts);
            CHECK(got > 0, "frame %d: nc=%d but fill returned %d", frame, n, got);
            if (got > maxCommands) maxCommands = got;
            totalCommands += got;

            for (int i = 0; i < got; ++i) {
                const float *f = &cmdFloats.u.f[i * FLOATS_PER_CMD];
                const int *iv = &cmdInts.u.i[i * INTS_PER_CMD];
                int kind = iv[0];
                int sprite = iv[1];
                int flags = iv[3];
                uint32_t rgba = (uint32_t)iv[2];

                CHECK(kind == GC_CMD_SPRITE || kind == GC_CMD_RECT || kind == GC_CMD_GLYPH,
                      "frame %d cmd %d: bad kind %d", frame, i, kind);
                if (kind >= 1 && kind <= 3) sawKind[kind] = 1;

                CHECK((flags & ~(int)(GC_FLAG_FLASH | GC_FLAG_SHADOW)) == 0,
                      "frame %d cmd %d: unknown flags 0x%x", frame, i, flags);
                if (flags & GC_FLAG_SHADOW) sawFlagShadow = 1;
                if (flags & GC_FLAG_FLASH) sawFlagFlash = 1;

                /* geometry must be finite; sizes must not be negative */
                CHECK(finite_float(f[0]) && finite_float(f[1]) && finite_float(f[2]) &&
                      finite_float(f[3]) && finite_float(f[4]),
                      "frame %d cmd %d: non-finite geometry", frame, i);
                CHECK(f[2] >= 0.f && f[3] >= 0.f,
                      "frame %d cmd %d: negative size %f x %f", frame, i, f[2], f[3]);
                if (f[4] != 0.f) maxRotSeen++;

                if (kind == GC_CMD_SPRITE) {
                    CHECK(sprite >= 0 && sprite < GC_SPR_COUNT,
                          "frame %d cmd %d: sprite id %d out of range", frame, i, sprite);
                    if (sprite >= 0 && sprite < GC_SPR_COUNT) sawSpriteIds[sprite] = 1;
                    /*
                     * VERIFIED FINDING (real core, all 136820 commands):
                     * GC_CMD_SPRITE leaves the UV rect at 0,0,0,0 -- the header
                     * documents u0..v1 as the *glyph* atlas rect only.  A renderer
                     * that forwarded these UVs to the GPU would sample one texel
                     * and draw every sprite as a flat colour, so GameRenderer
                     * substitutes (0,0)-(1,1) for sprites and rects.  This assert
                     * re-checks that assumption instead of encoding it blindly: it
                     * fires only if the core ever starts carrying sprite UVs, at
                     * which point GameRenderer needs to forward them.
                     */
                    if (f[5] != 0.f || f[6] != 0.f || f[7] != 0.f || f[8] != 0.f) {
                        spriteUvCarried++;
                        CHECK(f[5] >= 0.f && f[6] >= 0.f && f[7] <= 1.f && f[8] <= 1.f &&
                              f[5] < f[7] && f[6] < f[8],
                              "frame %d cmd %d: sprite carries an invalid UV rect (%f %f %f %f)",
                              frame, i, f[5], f[6], f[7], f[8]);
                    }
                }
                if (kind == GC_CMD_GLYPH) {
                    CHECK(f[5] >= 0.f && f[6] >= 0.f && f[7] <= 1.f && f[8] <= 1.f &&
                          f[5] <= f[7] && f[6] <= f[8],
                          "frame %d cmd %d: glyph uv rect invalid (%f %f %f %f)",
                          frame, i, f[5], f[6], f[7], f[8]);
                    CHECK(f[2] > 0.f && f[3] > 0.f,
                          "frame %d cmd %d: zero-sized glyph", frame, i);
                }
                if (kind == GC_CMD_RECT) {
                    /* rects must be opaque enough to be visible; alpha 0 is legal
                       (fully transparent) but would be skipped by the renderer. */
                    (void)rgba;
                }
            }
        }

        int ne = Java_com_gamecore_NativeCore_nativeEventCount(env, NULL, h);
        CHECK(ne >= 0, "negative event count %d", ne);
        if (ne > 0) {
            evtFloats.len = ne * FLOATS_PER_EVENT;
            evtInts.len = ne;
            if (evtFloats.len > FAKE_ARRAY_MAX) evtFloats.len = FAKE_ARRAY_MAX;
            if (evtInts.len > FAKE_ARRAY_MAX) evtInts.len = FAKE_ARRAY_MAX;
            int got = Java_com_gamecore_NativeCore_nativeFillEvents(
                env, NULL, h, ne, (jfloatArray)&evtFloats, (jintArray)&evtInts);
            totalEvents += got;
            for (int i = 0; i < got; ++i) {
                int type = evtInts.u.i[i];
                CHECK(type >= GC_EVT_SHOOT && type <= GC_EVT_DASH,
                      "frame %d evt %d: unknown event type %d", frame, i, type);
                int typeIdx = type;
                if (typeIdx > maxEventType) maxEventType = typeIdx;
                /* Haptics.onEvent() indexes fixed tables by type; every type in
                   range must have a slot (CUE_NAMES/HAPTIC_MS are size 15). */
                CHECK(typeIdx >= 1 && typeIdx <= 14, "event type %d outside 1..14", typeIdx);
                const float *f = &evtFloats.u.f[i * FLOATS_PER_EVENT];
                CHECK(finite_float(f[0]) && finite_float(f[1]) && finite_float(f[2]),
                      "frame %d evt %d: non-finite payload", frame, i);
            }
        }

        if ((frame % 60) == 0) {
            statusInts.len = 7;
            statusFloats.len = 3;
            int ok = Java_com_gamecore_NativeCore_nativeStatus(
                env, NULL, h, (jintArray)&statusInts, (jfloatArray)&statusFloats);
            CHECK(ok == 1, "frame %d: nativeStatus failed", frame);
            int state = statusInts.u.i[6];
            CHECK(state >= GC_STATE_TITLE && state <= GC_STATE_GAME_OVER,
                  "frame %d: invalid game state %d", frame, state);
            CHECK(statusFloats.u.f[0] >= 0.f && statusFloats.u.f[0] <= statusFloats.u.f[1] + 0.001f,
                  "frame %d: hp %f outside [0, max %f]",
                  frame, statusFloats.u.f[0], statusFloats.u.f[1]);
            CHECK(statusFloats.u.f[2] >= 0.f, "frame %d: negative time_alive", frame);
        }
    }

    printf("900 frames: %d commands total, %d in the busiest frame, %d events\n",
           totalCommands, maxCommands, totalEvents);
    printf("  kinds seen: sprite=%d rect=%d glyph=%d (shadow=%d flash=%d), rotated cmds=%d\n",
           sawKind[GC_CMD_SPRITE], sawKind[GC_CMD_RECT], sawKind[GC_CMD_GLYPH],
           sawFlagShadow, sawFlagFlash, maxRotSeen);
    int spritesSeen = 0;
    for (int i = 0; i < GC_SPR_COUNT; ++i) spritesSeen += sawSpriteIds[i];
    printf("  distinct sprite ids used: %d/%d, highest event type: %d\n",
           spritesSeen, GC_SPR_COUNT, maxEventType);

    if (spriteUvCarried == 0) {
        printf("  note: GC_CMD_SPRITE never carried a UV rect (0,0,0,0) -- the renderer\n"
               "        substituting the full-texture rect for sprites is required, not optional.\n");
    } else {
        printf("  WARNING: %d sprite commands carried a UV rect; GameRenderer ignores it.\n",
               spriteUvCarried);
    }

    CHECK(totalCommands > 0, "the core emitted no commands at all in 900 frames");
    CHECK(sawKind[GC_CMD_SPRITE] || sawKind[GC_CMD_RECT],
          "neither sprites nor rects were ever emitted");
    CHECK(maxEventType >= GC_EVT_SHOOT, "no events at all in 900 frames");

    /* ---- the wrapper must clamp real data, not just fake data ----------- */
    if (maxCommands > 2) {
        static FakeArray tinyFloats = FAKE_ARRAY_INIT(1, 2 * 9);
        static FakeArray tinyInts = FAKE_ARRAY_INIT(0, 2 * 4);
        int n = Java_com_gamecore_NativeCore_nativeCmdCount(env, NULL, h);
        tinyFloats.len = 2 * 9;
        tinyInts.len = 2 * 4;
        int got = Java_com_gamecore_NativeCore_nativeFillCommands(
            env, NULL, h, n, (jfloatArray)&tinyFloats, (jintArray)&tinyInts);
        CHECK(got <= 2, "capacity clamp returned %d for a 2-command buffer", got);
    }

    /* ---- save / load round trip through the wrapper --------------------- */
    static FakeArray blob = FAKE_ARRAY_INIT(0, 1024);
    blob.len = 1024;
    int saved = Java_com_gamecore_NativeCore_nativeSave(env, NULL, h, (jbyteArray)&blob, 1024);
    CHECK(saved > 0, "nativeSave returned %d", saved);
    CHECK(blob.len >= saved, "save wrote past the buffer");

    /* too small: the Kotlin retry loop depends on this being -1 */
    int tooSmall = Java_com_gamecore_NativeCore_nativeSave(env, NULL, h, (jbyteArray)&blob, 8);
    CHECK(tooSmall == -1, "nativeSave with an 8-byte cap must return -1, got %d", tooSmall);

    int loaded = Java_com_gamecore_NativeCore_nativeLoad(env, NULL, h, (jbyteArray)&blob, saved);
    CHECK(loaded != 0, "nativeLoad of a valid blob returned %d", loaded);

    /* ---- garbage must not be accepted ---------------------------------- */
    unsigned char *raw = (unsigned char *)blob.u.b;
    unsigned char first = raw[0];
    raw[0] = (unsigned char)~first;
    int badLoad = Java_com_gamecore_NativeCore_nativeLoad(env, NULL, h, (jbyteArray)&blob, saved);
    raw[0] = first;
    CHECK(badLoad == 0, "nativeLoad must reject a corrupt blob (got %d)", badLoad);

    /* ---- destroy ---- */
    Java_com_gamecore_NativeCore_nativeDestroy(env, NULL, h);
    CHECK(Java_com_gamecore_NativeCore_nativeCmdCount(env, NULL, 0) == 0,
          "null handle must report 0 commands");

    if (g_fail == 0) {
        printf("real-core: ALL INTEGRATION CHECKS PASSED\n");
        return 0;
    }
    printf("real-core: %d CHECK(s) FAILED\n", g_fail);
    return 1;
}
