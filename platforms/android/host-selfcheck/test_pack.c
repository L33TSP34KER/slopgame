/*
 * Host-only self-test #1: game_jni.c against a FAKE core.
 *
 * Checks the wrapper's own contract -- packing strides, slot order, capacity
 * clamping, null-handle behaviour, save/load retry -- with values chosen so that
 * every field is individually recognisable in the packed output.
 *
 * NOT part of the Android build.  Run through ./run.sh.
 */
#include <jni.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>

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

/* host stub for the single liblog symbol game_jni.c uses */
int __android_log_print(int prio, const char *tag, const char *fmt, ...)
{
    (void)prio; (void)tag; (void)fmt;
    return 0;
}

/* ---- fake core --------------------------------------------------------- */
static gc_cmd g_cmds[4];
static gc_event g_events[3];
static gc_status g_status;
static int g_updated = 0;
static float g_last_dt = 0.0f;
static gc_input g_last_input;
static int g_resize_calls = 0;

uint32_t gc_abi_version(void) { return GC_ABI_VERSION; }
gc_handle *gc_create(uint32_t seed) { return (gc_handle *)(intptr_t)(0x1000 + seed); }
void gc_destroy(gc_handle *h) { (void)h; }
void gc_resize(gc_handle *h, int32_t w, int32_t hh, float l, float t, float r, float b)
{
    (void)h; (void)w; (void)hh; (void)l; (void)t; (void)r; (void)b;
    g_resize_calls++;
}
void gc_virtual_size(const gc_handle *h, float *w, float *hh) { (void)h; *w = 1280.0f; *hh = 720.0f; }
float gc_view_scale(const gc_handle *h) { (void)h; return 1.5f; }
void gc_update(gc_handle *h, const gc_input *in, float dt)
{
    (void)h;
    g_updated++;
    g_last_dt = dt;
    g_last_input = *in;
}
const gc_cmd *gc_cmds(const gc_handle *h, int32_t *out) { (void)h; if (out) *out = 4; return g_cmds; }
const gc_event *gc_events(const gc_handle *h, int32_t *out) { (void)h; if (out) *out = 3; return g_events; }
void gc_status_get(const gc_handle *h, gc_status *out) { (void)h; *out = g_status; }
int32_t gc_save(const gc_handle *h, void *buf, int32_t cap)
{
    (void)h;
    if (cap < 5) return -1;
    memcpy(buf, "HELLO", 5);
    return 5;
}
int32_t gc_load(gc_handle *h, const void *buf, int32_t len) { (void)h; (void)buf; return len == 5 ? 0 : -1; }
void gc_debug(gc_handle *h, int32_t cmd, float value) { (void)h; (void)cmd; (void)value; }
const char *gc_sprite_file(int32_t s)
{
    static const char *names[GC_SPR_COUNT] = {
        "player.png", "enemy_a.png", "enemy_b.png", "gun.png",
        "bow.png", "sword.png", "money.png", "xp.png"
    };
    return (s >= 0 && s < GC_SPR_COUNT) ? names[s] : NULL;
}
void gc_font_atlas(const char **file, int32_t *w, int32_t *h)
{
    if (file) *file = "font_atlas.png";
    if (w) *w = 512;
    if (h) *h = 512;
}

/* ---- tests ------------------------------------------------------------- */
static int g_fail = 0;
#define CHECK(cond, ...) do { if (!(cond)) { printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); g_fail++; } } while (0)

int main(void)
{
    JNIEnv *env = fake_jni_env();

    /* ---- handle round trip ---- */
    jlong h = Java_com_gamecore_NativeCore_nativeCreate(env, NULL, 7);
    CHECK(h != 0, "nativeCreate returned 0");
    CHECK(Java_com_gamecore_NativeCore_nativeAbiVersion(env, NULL) == (jint)GC_ABI_VERSION,
          "abi version mismatch");

    /* ---- resize / scale ---- */
    Java_com_gamecore_NativeCore_nativeResize(env, NULL, h, 2400, 1080, 1.f, 2.f, 3.f, 4.f);
    CHECK(g_resize_calls == 1, "gc_resize not forwarded");
    CHECK(Java_com_gamecore_NativeCore_nativeViewScale(env, NULL, h) == 1.5f,
          "view scale not forwarded");
    CHECK(Java_com_gamecore_NativeCore_nativeViewScale(env, NULL, 0) == 1.0f,
          "null handle must yield scale 1.0");

    /* ---- update mirrors gc_input field order ---- */
    Java_com_gamecore_NativeCore_nativeUpdate(env, NULL, h, 0.016f,
                                              0.25f, -0.5f, 111.0f, 222.0f, 1, 0, 0x2);
    CHECK(g_updated == 1, "gc_update not forwarded");
    CHECK(g_last_dt == 0.016f, "dt not forwarded");
    CHECK(g_last_input.move_x == 0.25f && g_last_input.move_y == -0.5f, "move axis order wrong");
    CHECK(g_last_input.aim_x == 111.0f && g_last_input.aim_y == 222.0f, "aim order wrong");
    CHECK(g_last_input.pointer_active == 1 && g_last_input.pointer_down == 0, "pointer flags wrong");
    CHECK(g_last_input.buttons == 0x2u, "buttons wrong");

    /* ---- command packing ---- */
    g_cmds[0].kind = GC_CMD_SPRITE; g_cmds[0].sprite = GC_SPR_SWORD;
    g_cmds[0].x = 1.5f; g_cmds[0].y = 2.5f; g_cmds[0].w = 3.0f; g_cmds[0].h = 4.0f;
    g_cmds[0].rot = 0.75f; g_cmds[0].rgba = 0x80FF8040u; g_cmds[0].flags = GC_FLAG_SHADOW;
    g_cmds[0].u0 = 0.f; g_cmds[0].v0 = 0.f; g_cmds[0].u1 = 1.f; g_cmds[0].v1 = 1.f;
    g_cmds[1].kind = GC_CMD_GLYPH; g_cmds[1].sprite = 0;
    g_cmds[1].x = 9.f; g_cmds[1].y = 8.f; g_cmds[1].w = 7.f; g_cmds[1].h = 6.f;
    g_cmds[1].rot = 0.f; g_cmds[1].rgba = 0xFFFFFFFFu; g_cmds[1].flags = GC_FLAG_FLASH;
    g_cmds[1].u0 = 0.1f; g_cmds[1].v0 = 0.2f; g_cmds[1].u1 = 0.3f; g_cmds[1].v1 = 0.4f;
    g_cmds[2].kind = GC_CMD_RECT; g_cmds[2].sprite = -1;
    g_cmds[2].x = -1.f; g_cmds[2].y = -2.f; g_cmds[2].w = 0.f; g_cmds[2].h = 0.f;
    g_cmds[2].rot = 0.f; g_cmds[2].rgba = 0x11223344u; g_cmds[2].flags = GC_FLAG_NONE;
    g_cmds[3] = g_cmds[0];

    CHECK(Java_com_gamecore_NativeCore_nativeCmdCount(env, NULL, h) == 4, "cmd count wrong");

    FakeArray floats = FAKE_ARRAY_INIT(1, 4 * 9);
    FakeArray ints = FAKE_ARRAY_INIT(0, 4 * 4);
    jint written = Java_com_gamecore_NativeCore_nativeFillCommands(env, NULL, h, 4,
                                                                  (jfloatArray)&floats,
                                                                  (jintArray)&ints);
    CHECK(written == 4, "fill wrote %d, expected 4", (int)written);
    CHECK(floats.u.f[0] == 1.5f && floats.u.f[1] == 2.5f && floats.u.f[2] == 3.0f &&
          floats.u.f[3] == 4.0f && floats.u.f[4] == 0.75f,
          "cmd#0 x,y,w,h,rot packed wrong: %f %f %f %f %f",
          floats.u.f[0], floats.u.f[1], floats.u.f[2], floats.u.f[3], floats.u.f[4]);
    CHECK(floats.u.f[5] == 0.f && floats.u.f[6] == 0.f && floats.u.f[7] == 1.f && floats.u.f[8] == 1.f,
          "cmd#0 uv packed wrong");
    CHECK(ints.u.i[0] == GC_CMD_SPRITE && ints.u.i[1] == GC_SPR_SWORD, "cmd#0 kind/sprite wrong");
    CHECK((uint32_t)ints.u.i[2] == 0x80FF8040u, "cmd#0 rgba bit pattern wrong: %08x",
          (unsigned)ints.u.i[2]);
    CHECK(ints.u.i[3] == GC_FLAG_SHADOW, "cmd#0 flags wrong");

    /* cmd#1 floats occupy [9..17]: x,y,w,h,rot,u0,v0,u1,v1 */
    CHECK(floats.u.f[9] == 9.f && floats.u.f[10] == 8.f && floats.u.f[11] == 7.f &&
          floats.u.f[12] == 6.f && floats.u.f[13] == 0.f,
          "cmd#1 x,y,w,h,rot wrong");
    CHECK(floats.u.f[14] == 0.1f && floats.u.f[15] == 0.2f &&
          floats.u.f[16] == 0.3f && floats.u.f[17] == 0.4f,
          "cmd#1 uv rect wrong: %f %f %f %f",
          floats.u.f[14], floats.u.f[15], floats.u.f[16], floats.u.f[17]);
    CHECK(ints.u.i[4] == GC_CMD_GLYPH && ints.u.i[7] == GC_FLAG_FLASH, "cmd#1 ints wrong");
    CHECK(floats.u.f[22] == 0.f && ints.u.i[8] == GC_CMD_RECT && ints.u.i[9] == -1,
          "cmd#2 wrong");

    /* capacity clamps in *both* arrays */
    FakeArray small_f = FAKE_ARRAY_INIT(1, 2 * 9);
    FakeArray small_i = FAKE_ARRAY_INIT(0, 2 * 4);
    CHECK(Java_com_gamecore_NativeCore_nativeFillCommands(env, NULL, h, 4,
                                                          (jfloatArray)&small_f,
                                                          (jintArray)&small_i) == 2,
          "float capacity clamp failed");
    FakeArray clamp_i = FAKE_ARRAY_INIT(0, 1 * 4);
    FakeArray clamp_f = FAKE_ARRAY_INIT(1, 4 * 9);
    CHECK(Java_com_gamecore_NativeCore_nativeFillCommands(env, NULL, h, 4,
                                                          (jfloatArray)&clamp_f,
                                                          (jintArray)&clamp_i) == 1,
          "int capacity clamp failed");
    CHECK(Java_com_gamecore_NativeCore_nativeFillCommands(env, NULL, h, 3,
                                                          (jfloatArray)&clamp_f,
                                                          (jintArray)&ints) == 3,
          "count clamp failed");
    CHECK(Java_com_gamecore_NativeCore_nativeFillCommands(env, NULL, 0, 4,
                                                          (jfloatArray)&clamp_f,
                                                          (jintArray)&ints) == 0,
          "null handle must write nothing");

    /* ---- events ---- */
    g_events[0].type = GC_EVT_SHOOT; g_events[0].x = 10.f; g_events[0].y = 20.f; g_events[0].value = 0.f;
    g_events[1].type = GC_EVT_PLAYER_HURT; g_events[1].x = 1.f; g_events[1].y = 2.f; g_events[1].value = 7.5f;
    g_events[2].type = GC_EVT_GAME_OVER; g_events[2].x = 0.f; g_events[2].y = 0.f; g_events[2].value = 1234.f;
    CHECK(Java_com_gamecore_NativeCore_nativeEventCount(env, NULL, h) == 3, "event count wrong");
    FakeArray ef = FAKE_ARRAY_INIT(1, 3 * 3);
    FakeArray ei = FAKE_ARRAY_INIT(0, 3 * 1);
    CHECK(Java_com_gamecore_NativeCore_nativeFillEvents(env, NULL, h, 3,
                                                        (jfloatArray)&ef, (jintArray)&ei) == 3,
          "event fill failed");
    CHECK(ei.u.i[0] == GC_EVT_SHOOT && ei.u.i[2] == GC_EVT_GAME_OVER, "event types wrong");
    CHECK(ef.u.f[3] == 1.f && ef.u.f[4] == 2.f && ef.u.f[5] == 7.5f, "event x/y/value wrong");

    /* ---- status ---- */
    g_status.wave = 3; g_status.level = 4; g_status.kills = 5; g_status.money = 6;
    g_status.score = 7; g_status.best_score = 8; g_status.state = GC_STATE_SHOP;
    g_status.player_hp = 42.5f; g_status.player_hp_max = 100.f; g_status.time_alive = 12.25f;
    FakeArray si = FAKE_ARRAY_INIT(0, 7);
    FakeArray sf = FAKE_ARRAY_INIT(1, 3);
    CHECK(Java_com_gamecore_NativeCore_nativeStatus(env, NULL, h, (jintArray)&si, (jfloatArray)&sf) == 1,
          "status failed");
    CHECK(si.u.i[0] == 3 && si.u.i[1] == 4 && si.u.i[5] == 8 && si.u.i[6] == GC_STATE_SHOP,
          "status ints wrong");
    CHECK(sf.u.f[0] == 42.5f && sf.u.f[1] == 100.f && sf.u.f[2] == 12.25f, "status floats wrong");
    FakeArray tiny = FAKE_ARRAY_INIT(0, 3);
    CHECK(Java_com_gamecore_NativeCore_nativeStatus(env, NULL, h, (jintArray)&tiny, (jfloatArray)&sf) == 0,
          "status must refuse too-small arrays");

    /* ---- save / load (including the grow-and-retry contract) ---- */
    FakeArray blob = FAKE_ARRAY_INIT(0, 4);
    CHECK(Java_com_gamecore_NativeCore_nativeSave(env, NULL, h, (jbyteArray)&blob, 4) == -1,
          "save must report -1 when the blob does not fit");
    FakeArray blob2 = FAKE_ARRAY_INIT(0, 64);
    CHECK(Java_com_gamecore_NativeCore_nativeSave(env, NULL, h, (jbyteArray)&blob2, 64) == 5,
          "save should write 5 bytes");
    CHECK(memcmp(blob2.u.b, "HELLO", 5) == 0, "save blob content wrong");
    CHECK(Java_com_gamecore_NativeCore_nativeLoad(env, NULL, h, (jbyteArray)&blob2, 5) == 0,
          "load should succeed");
    CHECK(Java_com_gamecore_NativeCore_nativeLoad(env, NULL, 0, (jbyteArray)&blob2, 5) == -1,
          "load with null handle must fail");

    /* ---- debug / destroy ---- */
    Java_com_gamecore_NativeCore_nativeDebug(env, NULL, h, GC_DBG_GIVE_MONEY, 100.f);
    Java_com_gamecore_NativeCore_nativeDestroy(env, NULL, h);
    Java_com_gamecore_NativeCore_nativeDestroy(env, NULL, 0); /* must not crash */

    /* ---- asset names ---- */
    jobjectArray names = Java_com_gamecore_NativeCore_nativeAssetNames(env, NULL);
    CHECK((intptr_t)names == GC_SPR_COUNT + 1, "asset name array must have SPR_COUNT+1 entries");

    if (g_fail == 0) {
        printf("fake-core: ALL JNI WRAPPER SELF-TESTS PASSED "
               "(cmd stride 9 floats/4 ints, event 3/1, status 7/3)\n");
        return 0;
    }
    printf("fake-core: %d CHECK(s) FAILED\n", g_fail);
    return 1;
}
