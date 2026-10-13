/*
 * harness.c -- C ABI conformance test for libgame_core.
 *
 * This is the "third party" check on the architecture: it is written in C, it
 * includes include/game_core.h, it dlopen()s the built shared library, and it
 * drives a whole game through the public ABI exactly like a platform renderer
 * does.  If the header drifts from the library, or a renderer's assumptions are
 * wrong, this fails.
 *
 * Build + run:  tools/run_abi_harness.sh
 */
#include <dlfcn.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "game_core.h"

/* ------------------------------------------------------------------ */
/* the header must describe the same bytes the library was built with  */
/* ------------------------------------------------------------------ */

_Static_assert(sizeof(gc_cmd) == 56, "gc_cmd must be 56 bytes");
_Static_assert(_Alignof(gc_cmd) == 4, "gc_cmd must be 4-byte aligned");
_Static_assert(offsetof(gc_cmd, kind) == 0, "gc_cmd.kind");
_Static_assert(offsetof(gc_cmd, sprite) == 4, "gc_cmd.sprite");
_Static_assert(offsetof(gc_cmd, x) == 8, "gc_cmd.x");
_Static_assert(offsetof(gc_cmd, y) == 12, "gc_cmd.y");
_Static_assert(offsetof(gc_cmd, w) == 16, "gc_cmd.w");
_Static_assert(offsetof(gc_cmd, h) == 20, "gc_cmd.h");
_Static_assert(offsetof(gc_cmd, rot) == 24, "gc_cmd.rot");
_Static_assert(offsetof(gc_cmd, rgba) == 28, "gc_cmd.rgba");
_Static_assert(offsetof(gc_cmd, u0) == 32, "gc_cmd.u0");
_Static_assert(offsetof(gc_cmd, v0) == 36, "gc_cmd.v0");
_Static_assert(offsetof(gc_cmd, u1) == 40, "gc_cmd.u1");
_Static_assert(offsetof(gc_cmd, v1) == 44, "gc_cmd.v1");
_Static_assert(offsetof(gc_cmd, flags) == 48, "gc_cmd.flags");
_Static_assert(offsetof(gc_cmd, _pad) == 52, "gc_cmd._pad");
_Static_assert(sizeof(gc_input) == 28, "gc_input must be 28 bytes");
_Static_assert(sizeof(gc_event) == 16, "gc_event must be 16 bytes");
_Static_assert(sizeof(gc_status) == 40, "gc_status must be 40 bytes");
_Static_assert(sizeof(gc_rect) == 16, "gc_rect must be 16 bytes");
_Static_assert(sizeof(gc_progress) == 16, "gc_progress must be 16 bytes");
_Static_assert(GC_SPR_COUNT == 21, "sprite count");

/* ------------------------------------------------------------------ */
/* entry points resolved from the shared library                       */
/* ------------------------------------------------------------------ */

typedef struct {
    uint32_t (*abi_version)(void);
    gc_handle *(*create)(uint32_t seed);
    void (*destroy)(gc_handle *);
    void (*resize)(gc_handle *, int32_t, int32_t, float, float, float, float);
    void (*virtual_size)(const gc_handle *, float *, float *);
    float (*view_scale)(const gc_handle *);
    void (*update)(gc_handle *, const gc_input *, float);
    const gc_cmd *(*cmds)(const gc_handle *, int32_t *);
    const gc_event *(*events)(const gc_handle *, int32_t *);
    void (*status_get)(const gc_handle *, gc_status *);
    void (*progress_get)(const gc_handle *, gc_progress *);
    const char *(*sprite_file)(int32_t);
    void (*font_atlas)(const char **, int32_t *, int32_t *);
    int32_t (*save)(const gc_handle *, void *, int32_t);
    int32_t (*load)(gc_handle *, const void *, int32_t);
    void (*debug)(gc_handle *, int32_t, float);
    gc_rect (*ui_slot)(const gc_handle *, int32_t);
    int32_t (*ui_slot_count)(const gc_handle *);
    gc_rect (*ui_button)(const gc_handle *, int32_t);
    int32_t (*market_open)(const gc_handle *);
    void (*market_set_open)(gc_handle *, int32_t);
    int32_t (*settings_get)(const gc_handle *, gc_settings *);
    int32_t (*options_open)(const gc_handle *);
    void (*options_set_open)(gc_handle *, int32_t);
    int32_t (*tree_count)(void);
    gc_rect (*tree_rect)(const gc_handle *, int32_t);
    int32_t (*tree_state)(const gc_handle *, int32_t);
    int32_t (*tree_cost)(const gc_handle *, int32_t);
} api_t;

static int failures = 0;

#define CHECK(cond, ...)                                                       \
    do {                                                                       \
        if (!(cond)) {                                                         \
            failures++;                                                        \
            printf("  FAIL %s:%d: ", __FILE__, __LINE__);                      \
            printf(__VA_ARGS__);                                               \
            printf("\n");                                                      \
        }                                                                      \
    } while (0)

static void *must_symbol(void *lib, const char *name)
{
    void *p = dlsym(lib, name);
    if (!p) {
        fprintf(stderr, "missing symbol %s: %s\n", name, dlerror());
        exit(2);
    }
    return p;
}

#define RESOLVE(field, name)                                                   \
    do {                                                                       \
        void *sym_ = must_symbol(lib, name);                                   \
        memcpy(&api->field, &sym_, sizeof(sym_));                              \
    } while (0)

static void resolve_api(void *lib, api_t *api)
{
    RESOLVE(abi_version, "gc_abi_version");
    RESOLVE(create, "gc_create");
    RESOLVE(destroy, "gc_destroy");
    RESOLVE(resize, "gc_resize");
    RESOLVE(virtual_size, "gc_virtual_size");
    RESOLVE(view_scale, "gc_view_scale");
    RESOLVE(update, "gc_update");
    RESOLVE(cmds, "gc_cmds");
    RESOLVE(events, "gc_events");
    RESOLVE(status_get, "gc_status_get");
    RESOLVE(progress_get, "gc_progress_get");
    RESOLVE(sprite_file, "gc_sprite_file");
    RESOLVE(font_atlas, "gc_font_atlas");
    RESOLVE(save, "gc_save");
    RESOLVE(load, "gc_load");
    RESOLVE(debug, "gc_debug");
    RESOLVE(ui_slot, "gc_ui_slot");
    RESOLVE(ui_slot_count, "gc_ui_slot_count");
    RESOLVE(ui_button, "gc_ui_button");
    RESOLVE(market_open, "gc_market_open");
    RESOLVE(market_set_open, "gc_market_set_open");
    RESOLVE(settings_get, "gc_settings_get");
    RESOLVE(options_open, "gc_options_open");
    RESOLVE(options_set_open, "gc_options_set_open");
    RESOLVE(tree_count, "gc_tree_count");
    RESOLVE(tree_rect, "gc_tree_rect");
    RESOLVE(tree_state, "gc_tree_state");
    RESOLVE(tree_cost, "gc_tree_cost");
}

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

static const gc_input NEUTRAL = {0};

static gc_input neutral_input(void)
{
    return NEUTRAL;
}

/* One update + a full inspection of the frame it produced. */
static void step_and_check(const api_t *api, gc_handle *h, const gc_input *in,
                           float dt, int frame, int *sprites, int *glyphs, int *rects)
{
    api->update(h, in, dt);

    int32_t count = 0;
    const gc_cmd *cmds = api->cmds(h, &count);
    CHECK(cmds != NULL, "gc_cmds returned NULL on frame %d", frame);
    if (!cmds || count <= 0) {
        CHECK(count > 0, "frame %d produced no commands", frame);
        return;
    }

    for (int32_t i = 0; i < count; i++) {
        const gc_cmd *c = &cmds[i];
        CHECK(isfinite(c->x) && isfinite(c->y) && isfinite(c->w) && isfinite(c->h) &&
                  isfinite(c->rot),
              "frame %d command %d has a non-finite field", frame, i);
        CHECK(c->w > 0.0f && c->h > 0.0f, "frame %d command %d has an empty quad", frame, i);
        switch (c->kind) {
        case GC_CMD_SPRITE:
            (*sprites)++;
            CHECK(c->sprite >= 0 && c->sprite < GC_SPR_COUNT,
                  "frame %d command %d: sprite id %d out of range", frame, i, c->sprite);
            break;
        case GC_CMD_GLYPH:
            (*glyphs)++;
            CHECK(c->u0 >= 0.0f && c->v0 >= 0.0f && c->u1 <= 1.0001f && c->v1 <= 1.0001f,
                  "frame %d command %d: glyph uv out of range", frame, i);
            CHECK(c->u1 > c->u0 && c->v1 > c->v0,
                  "frame %d command %d: empty glyph uv", frame, i);
            break;
        case GC_CMD_RECT:
            (*rects)++;
            break;
        default:
            CHECK(0, "frame %d command %d: unknown kind %d", frame, i, c->kind);
        }
    }

    int32_t events = 0;
    const gc_event *ev = api->events(h, &events);
    CHECK(ev != NULL, "gc_events returned NULL on frame %d", frame);
    for (int32_t i = 0; i < events; i++) {
        CHECK(isfinite(ev[i].x) && isfinite(ev[i].y) && isfinite(ev[i].value),
              "frame %d event %d has a non-finite field", frame, i);
    }
}

static void click(const api_t *api, gc_handle *h, float x, float y, int frame,
                  int *sprites, int *glyphs, int *rects)
{
    gc_input in = neutral_input();
    in.aim_x = x;
    in.aim_y = y;
    in.pointer_active = 1;
    in.pointer_down = 1;
    step_and_check(api, h, &in, 1.0f / 60.0f, frame, sprites, glyphs, rects);
    step_and_check(api, h, &in, 1.0f / 60.0f, frame + 1, sprites, glyphs, rects);
    in.pointer_down = 0; /* release without moving: a tap, not a drag */
    step_and_check(api, h, &in, 1.0f / 60.0f, frame + 2, sprites, glyphs, rects);
}

/* ------------------------------------------------------------------ */

int main(int argc, char **argv)
{
    const char *lib_path = argc > 1 ? argv[1] : "target/debug/libgame_core.so";

    printf("Slime Arena -- C ABI harness\n");
    printf("  library: %s\n", lib_path);
    printf("  header : gc_cmd=%zu gc_input=%zu gc_event=%zu gc_status=%zu gc_rect=%zu\n",
           sizeof(gc_cmd), sizeof(gc_input), sizeof(gc_event), sizeof(gc_status),
           sizeof(gc_rect));

    void *lib = dlopen(lib_path, RTLD_NOW);
    if (!lib) {
        fprintf(stderr, "dlopen failed: %s\n", dlerror());
        return 2;
    }

    api_t api;
    resolve_api(lib, &api);

    /* -- version and assets ------------------------------------------- */
    CHECK(api.abi_version() == GC_ABI_VERSION,
          "library ABI %u != header ABI %u", api.abi_version(), GC_ABI_VERSION);

    for (int32_t i = 0; i < GC_SPR_COUNT; i++) {
        const char *name = api.sprite_file(i);
        CHECK(name != NULL, "sprite %d has no file name", i);
        if (name) {
            CHECK(strstr(name, ".png") != NULL, "sprite %d name %s is not a png", i, name);
        }
    }
    CHECK(api.sprite_file(-1) == NULL, "sprite -1 must be NULL");
    CHECK(api.sprite_file(GC_SPR_COUNT) == NULL, "sprite out of range must be NULL");

    const char *atlas = NULL;
    int32_t aw = 0, ah = 0;
    api.font_atlas(&atlas, &aw, &ah);
    CHECK(atlas != NULL && aw > 0 && ah > 0, "font atlas missing");

    /* -- null safety --------------------------------------------------- */
    api.destroy(NULL);
    api.update(NULL, NULL, 0.016f);
    api.resize(NULL, 100, 100, 0, 0, 0, 0);
    CHECK(api.cmds(NULL, NULL) == NULL, "gc_cmds(NULL) must be NULL");
    CHECK(api.events(NULL, NULL) == NULL, "gc_events(NULL) must be NULL");
    CHECK(api.save(NULL, NULL, 0) == -1, "gc_save(NULL) must fail");

    /* -- a whole game through the ABI ---------------------------------- */
    gc_handle *h = api.create(20240607u);
    CHECK(h != NULL, "gc_create returned NULL");

    api.resize(h, 1280, 720, 0, 0, 0, 0);
    float vw = 0, vh = 0, scale = 0;
    api.virtual_size(h, &vw, &vh);
    scale = api.view_scale(h);
    CHECK(fabsf(vw - 1280.0f) < 0.5f, "virtual width %f", vw);
    CHECK(fabsf(vh - 720.0f) < 0.5f, "virtual height %f", vh);
    CHECK(fabsf(scale - 1.0f) < 1e-4f, "view scale %f", scale);

    /* A 2x display must keep the virtual size and double the scale. */
    api.resize(h, 2560, 1440, 0, 0, 0, 0);
    api.virtual_size(h, &vw, &vh);
    scale = api.view_scale(h);
    CHECK(fabsf(vw - 1280.0f) < 0.5f && fabsf(vh - 720.0f) < 0.5f,
          "2x display changed the virtual size: %fx%f", vw, vh);
    CHECK(fabsf(scale - 2.0f) < 1e-3f, "2x display scale %f", scale);
    api.resize(h, 1280, 720, 0, 0, 0, 0);

    int sprites = 0, glyphs = 0, rects = 0;
    int frame = 0;

    /* Title screen. */
    gc_input in = neutral_input();
    for (frame = 0; frame < 5; frame++) {
        step_and_check(&api, h, &in, 1.0f / 60.0f, frame, &sprites, &glyphs, &rects);
    }
    gc_status st;
    api.status_get(h, &st);
    CHECK(st.state == GC_STATE_TITLE, "expected the title state, got %d", st.state);
    CHECK(glyphs > 100, "the title screen should draw text (glyphs=%d)", glyphs);

    /* Click "start" using the rectangle the library reports. */
    gc_rect start = api.ui_button(h, 0);
    CHECK(start.w > 0 && start.h > 0, "start button has no rect");
    CHECK(start.x >= 0 && start.x + start.w <= vw + 1.0f, "start button outside the view");
    click(&api, h, start.x + start.w * 0.5f, start.y + start.h * 0.5f, frame, &sprites,
          &glyphs, &rects);
    frame += 2;
    api.status_get(h, &st);
    CHECK(st.state == GC_STATE_PLAYING, "clicking start must begin a run (state=%d)", st.state);

    /* Fight for a few seconds with the starter weapon. */
    api.debug(h, GC_DBG_INVULNERABLE, 1.0f);
    api.debug(h, GC_DBG_SET_WAVE, 6.0f);
    api.debug(h, GC_DBG_GIVE_MONEY, 1000.0f);
    api.debug(h, GC_DBG_GIVE_WEAPON, 1.0f);
    api.debug(h, GC_DBG_GIVE_WEAPON, 2.0f);
    for (int i = 0; i < 600; i++, frame++) {
        in = neutral_input();
        in.pointer_active = 1;
        in.move_x = cosf((float)frame * 0.02f);
        in.move_y = sinf((float)frame * 0.02f);
        in.aim_x = 640.0f + cosf((float)frame * 0.05f) * 200.0f;
        in.aim_y = 360.0f + sinf((float)frame * 0.05f) * 120.0f;
        in.buttons = (i == 300) ? GC_BTN_DASH : 0u;
        step_and_check(&api, h, &in, 1.0f / 60.0f, frame, &sprites, &glyphs, &rects);
    }
    api.status_get(h, &st);
    CHECK(st.kills > 0, "auto-fire should have killed something (kills=%d)", st.kills);
    CHECK(st.score > 0, "score should be positive");

    /* Poisoned input: NaN and infinities must not break the frame. */
    in = neutral_input();
    in.move_x = NAN;
    in.move_y = INFINITY;
    in.aim_x = NAN;
    in.aim_y = -INFINITY;
    in.pointer_active = 1;
    in.pointer_down = 1;
    step_and_check(&api, h, &in, 1.0f / 60.0f, frame++, &sprites, &glyphs, &rects);
    step_and_check(&api, h, &in, NAN, frame++, &sprites, &glyphs, &rects);
    step_and_check(&api, h, &in, 1000.0f, frame++, &sprites, &glyphs, &rects);

    /* Level up: three cards, all clickable, all inside the view. */
    api.debug(h, GC_DBG_LEVEL_UP, 0.0f);
    step_and_check(&api, h, &NEUTRAL, 1.0f / 60.0f, frame++, &sprites, &glyphs, &rects);
    api.status_get(h, &st);
    CHECK(st.state == GC_STATE_LEVEL_UP, "expected the level-up state, got %d", st.state);
    CHECK(api.ui_slot_count(h) == 3, "a level-up should offer 3 cards");
    gc_rect card = api.ui_slot(h, 0);
    CHECK(card.w > 0 && card.h > 0, "card rect missing");
    CHECK(card.x >= 0 && card.x + card.w <= vw + 1.0f &&
              card.y >= 0 && card.y + card.h <= vh + 1.0f, "card outside the view");
    click(&api, h, card.x + card.w * 0.5f, card.y + card.h * 0.5f, frame, &sprites, &glyphs,
          &rects);
    frame += 3;
    api.status_get(h, &st);
    CHECK(st.state == GC_STATE_PLAYING, "picking a card should resume play (state=%d)", st.state);

    /* Clear the wave: the between-round screen is an upgrade tree. */
    api.debug(h, GC_DBG_SKIP_WAVE, 0.0f);
    for (int i = 0; i < 200 && st.state != GC_STATE_SHOP; i++, frame++) {
        step_and_check(&api, h, &NEUTRAL, 1.0f / 60.0f, frame, &sprites, &glyphs, &rects);
        api.status_get(h, &st);
    }
    CHECK(st.state == GC_STATE_SHOP, "clearing a wave should open the hive (state=%d)", st.state);

    int32_t nodes = api.tree_count();
    CHECK(nodes >= 200, "the upgrade tree should have at least 200 nodes (has %d)", nodes);

    /* Find the cheapest node we can actually buy, through the public ABI. */
    int32_t buyable = -1;
    int32_t buyable_cost = 0;
    for (int32_t node = 0; node < nodes; node++) {
        if (api.tree_state(h, node) != 2) {
            continue;
        }
        gc_rect r = api.tree_rect(h, node);
        int32_t c = api.tree_cost(h, node);
        if (r.w <= 0.0f || c < 0) {
            continue;
        }
        if (buyable < 0 || c < buyable_cost) {
            buyable = node;
            buyable_cost = c;
        }
    }
    CHECK(buyable >= 0, "at least one node must be purchasable");

    if (buyable >= 0) {
        gc_rect r = api.tree_rect(h, buyable);
        int32_t money_before = st.money;
        click(&api, h, r.x + r.w * 0.5f, r.y + r.h * 0.5f, frame, &sprites, &glyphs, &rects);
        frame += 3;
        api.status_get(h, &st);
        CHECK(st.money == money_before - buyable_cost,
              "buying node %d should cost exactly %d (%d -> %d)",
              buyable, buyable_cost, money_before, st.money);
        CHECK(api.tree_state(h, buyable) == 3, "the node should now be owned");
        CHECK(st.state == GC_STATE_SHOP, "buying keeps the hive open (state=%d)", st.state);

        /* Tapping a locked node must buy nothing, however cheap it looks. */
        int32_t locked = -1;
        for (int32_t node = 0; node < nodes; node++) {
            gc_rect r = api.tree_rect(h, node);
            if (api.tree_state(h, node) == 1 && r.w > 0.0f) {
                locked = node;
                break;
            }
        }
        CHECK(locked >= 0, "some node should be visibly locked");
        if (locked >= 0) {
            gc_rect r = api.tree_rect(h, locked);
            int32_t money_before = st.money;
            click(&api, h, r.x + r.w * 0.5f, r.y + r.h * 0.5f, frame, &sprites, &glyphs, &rects);
            frame += 3;
            api.status_get(h, &st);
            CHECK(st.money == money_before,
                  "a locked node must not be purchasable (%d -> %d)", money_before, st.money);
            CHECK(api.tree_state(h, locked) == 1, "the locked node must still be locked");
        }
    }

    /* Panning must not spend money: press, drag far, release. */
    {
        int32_t money_before = st.money;
        gc_input drag = neutral_input();
        drag.pointer_active = 1;
        drag.pointer_down = 1;
        drag.aim_x = 640.0f;
        drag.aim_y = 300.0f;
        step_and_check(&api, h, &drag, 1.0f / 60.0f, frame++, &sprites, &glyphs, &rects);
        drag.aim_x = 500.0f;
        drag.aim_y = 200.0f;
        step_and_check(&api, h, &drag, 1.0f / 60.0f, frame++, &sprites, &glyphs, &rects);
        drag.pointer_down = 0;
        step_and_check(&api, h, &drag, 1.0f / 60.0f, frame++, &sprites, &glyphs, &rects);
        api.status_get(h, &st);
        CHECK(st.money == money_before, "a drag must never buy anything (%d -> %d)",
              money_before, st.money);
    }

    /* The root node exists, is owned, and the tree is rooted at it. */
    CHECK(api.tree_state(h, 0) == 3, "the root node should be owned from the start");

    /* Start the next wave. */
    gc_rect next = api.ui_button(h, 1);
    CHECK(next.w > 0 && next.h > 0, "next-wave button has no rect");
    click(&api, h, next.x + next.w * 0.5f, next.y + next.h * 0.5f, frame, &sprites, &glyphs,
          &rects);
    frame += 3;
    api.status_get(h, &st);
    CHECK(st.state == GC_STATE_PLAYING, "next wave should resume play (state=%d)", st.state);

    /* Pause and resume. */
    in = neutral_input();
    in.buttons = GC_BTN_PAUSE;
    step_and_check(&api, h, &in, 1.0f / 60.0f, frame++, &sprites, &glyphs, &rects);
    api.status_get(h, &st);
    CHECK(st.state == GC_STATE_PAUSED, "pause should pause (state=%d)", st.state);
    step_and_check(&api, h, &NEUTRAL, 1.0f / 60.0f, frame++, &sprites, &glyphs, &rects);
    in.buttons = GC_BTN_PAUSE;
    step_and_check(&api, h, &in, 1.0f / 60.0f, frame++, &sprites, &glyphs, &rects);
    api.status_get(h, &st);
    CHECK(st.state == GC_STATE_PLAYING, "pause again should resume (state=%d)", st.state);

    /* Die first: the best score is only banked when the run ends. */
    api.debug(h, GC_DBG_KILL_PLAYER, 0.0f);
    step_and_check(&api, h, &NEUTRAL, 1.0f / 60.0f, frame++, &sprites, &glyphs, &rects);
    api.status_get(h, &st);
    CHECK(st.state == GC_STATE_GAME_OVER, "expected game over (state=%d)", st.state);
    CHECK(st.best_score > 0, "a best score should have been banked");

    unsigned char blob[64];
    int32_t written = api.save(h, blob, (int32_t)sizeof(blob));
    CHECK(written > 0, "gc_save failed");
    CHECK(memcmp(blob, "SLA1", 4) == 0, "save blob is not self describing");

    /* A fresh instance restores it. */
    gc_handle *h2 = api.create(1u);
    api.resize(h2, 1280, 720, 0, 0, 0, 0);
    gc_status st2;
    api.status_get(h2, &st2);
    CHECK(st2.best_score == 0, "a fresh instance starts with no best score");
    CHECK(api.load(h2, blob, written) == 1, "gc_load should accept our own blob");
    api.status_get(h2, &st2);
    CHECK(st2.best_score == st.best_score, "best score did not survive the round trip");
    unsigned char junk[32];
    memset(junk, 0xFF, sizeof(junk));
    CHECK(api.load(h2, junk, (int32_t)sizeof(junk)) == 0, "garbage must be rejected");
    api.destroy(h2);

    /* Restart from the game-over screen. */
    for (int i = 0; i < 60; i++, frame++) {
        step_and_check(&api, h, &NEUTRAL, 1.0f / 60.0f, frame, &sprites, &glyphs, &rects);
    }
    gc_rect again = api.ui_button(h, 0);
    click(&api, h, again.x + again.w * 0.5f, again.y + again.h * 0.5f, frame, &sprites, &glyphs,
          &rects);
    frame += 2;
    api.status_get(h, &st);
    CHECK(st.state == GC_STATE_PLAYING, "play again should restart (state=%d)", st.state);

    api.destroy(h);
    dlclose(lib);

    printf("  frames simulated : %d\n", frame);
    printf("  commands checked : %d sprite, %d glyph, %d rect\n", sprites, glyphs, rects);
    if (failures == 0) {
        printf("ABI HARNESS PASSED\n");
        return 0;
    }
    printf("ABI HARNESS FAILED: %d problem(s)\n", failures);
    return 1;
}
