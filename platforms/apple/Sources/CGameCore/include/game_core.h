/*
 * game_core.h -- C ABI of the shared game logic library.
 *
 * ARCHITECTURE
 * ------------
 * All gameplay (simulation, AI, collision, waves, economy, progression, HUD
 * layout, camera, particles and text layout) lives inside the shared library
 * (libgame_core.so / .dylib / .a / .so on Android).  Platform renderers are
 * deliberately thin: they own a window, a GPU context, the sprite textures, the
 * font atlas, an input loop and a speaker.  Every frame they
 *
 *   1. fill a gc_input and call gc_update(),
 *   2. read the flat, pre-sorted, screen-space command list with gc_cmds(),
 *   3. draw it with their native API (SDL_Renderer / Metal / OpenGL ES),
 *   4. read gc_events() and turn events into sound and haptics.
 *
 * Renderers never do game maths, never touch the camera and never lay out text.
 *
 * COORDINATES
 * -----------
 * Commands are emitted in *virtual units*, y-down, origin at the top-left of
 * the framebuffer.  The library keeps the design height fixed at
 * GC_DESIGN_HEIGHT virtual units, so
 *
 *     scale  = framebuffer_height_px / GC_DESIGN_HEIGHT
 *     pixel  = virtual * scale
 *
 * gc_view_scale() returns that single scale factor; there is no letterboxing and
 * no offset.  Renderers apply it as a uniform scale to a full-screen quad
 * (vertex * scale) or as an orthographic projection, and use the inverse to turn
 * touches into the virtual aim position.
 *
 * Commands are already in painter's order: draw them front to back, in the order
 * they are returned.  (x, y) is always the CENTER of the quad; `rot` rotates the
 * quad clockwise about that center.
 *
 * MEMORY / LIFETIME
 * -----------------
 * gc_cmds() and gc_events() return pointers to library-owned memory that stays
 * valid until the next gc_update() call.  `gc_cmd::text` is not exposed: the
 * library expands text into glyphs itself, so renderers only ever blit quads.
 *
 * All entry points are thread-affine to the thread that called gc_create().
 */
#ifndef GAME_CORE_H
#define GAME_CORE_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/* version / opaque handle                                            */
/* ------------------------------------------------------------------ */

#define GC_ABI_VERSION 1u

/* Virtual design height.  Keep in sync with core/src/lib.rs. */
#define GC_DESIGN_HEIGHT 720.0f

typedef struct gc_handle gc_handle;

/* Returns GC_ABI_VERSION.  A renderer must refuse to run on a mismatch. */
uint32_t gc_abi_version(void);

/* ------------------------------------------------------------------ */
/* assets the renderer must load                                      */
/* ------------------------------------------------------------------ */

/* Sprite ids.  Index into the table returned by gc_sprite_file(). */
typedef enum {
    GC_SPR_PLAYER = 0,
    GC_SPR_ENEMY_A,
    GC_SPR_ENEMY_B,
    GC_SPR_GUN,
    GC_SPR_BOW,
    GC_SPR_SWORD,
    GC_SPR_MONEY,
    GC_SPR_XP,
    GC_SPR_CHARGER, /* winds up, then dashes */
    GC_SPR_SPITTER, /* keeps its distance, throws blood */
    GC_SPR_MISER,   /* eats your money */
    GC_SPR_WISP,    /* circles you, never closes */
    GC_SPR_BLOB,    /* splits into grunts when killed */
    GC_SPR_BULWARK, /* 45% armour, very slow */
    GC_SPR_MENDER,  /* mends every enemy around it */
    GC_SPR_BOOMSLIME, /* explodes when killed */
    GC_SPR_SHADE,   /* blinks toward you */
    GC_SPR_LANCER,  /* long-range sniper */
    GC_SPR_DEVOURER, /* grows stronger while alive */
    GC_SPR_LEECH,   /* heals itself by hurting you */
    GC_SPR_SPIKER,  /* leaves caltrops */
    GC_SPR_COUNT
} gc_sprite_id;

/* File name (no directory) of a sprite, e.g. "player.png".
 * Returns NULL for out-of-range ids.  Textures are tight-trimmed RGBA PNGs;
 * always sample them with bilinear filtering, never clamp to a palette. */
const char *gc_sprite_file(int32_t sprite);

/* File name and pixel size of the white-on-transparent font atlas.
 * The library emits GC_CMD_GLYPH commands with normalised atlas UVs, so the
 * renderer only has to bind this one texture. */
void gc_font_atlas(const char **file, int32_t *width, int32_t *height);

/* ------------------------------------------------------------------ */
/* draw commands                                                      */
/* ------------------------------------------------------------------ */

typedef enum {
    GC_CMD_SPRITE = 1, /* textured quad from a sprite PNG      */
    GC_CMD_RECT   = 2, /* solid colour quad (UI, floor, bars)  */
    GC_CMD_GLYPH  = 3  /* one glyph from the font atlas        */
} gc_cmd_kind;

/* Flags packed into gc_cmd::flags */
#define GC_FLAG_NONE   0u
#define GC_FLAG_FLASH  1u /* additive blend, use it for muzzle flashes / hit sparks */
#define GC_FLAG_SHADOW 2u /* drop a soft dark offset copy (HUD text readability)     */

typedef struct {
    int32_t  kind;   /* gc_cmd_kind                                            */
    int32_t  sprite; /* gc_sprite_id, GC_CMD_SPRITE only                       */
    float    x, y;   /* CENTER of the quad, virtual units                      */
    float    w, h;   /* size in virtual units                                  */
    float    rot;    /* clockwise radians about (x, y)                         */
    uint32_t rgba;   /* 0xAARRGGBB premultiplied-free straight alpha           */
    float    u0, v0, u1, v1; /* GC_CMD_GLYPH: atlas UV rect                    */
    int32_t  flags;  /* GC_FLAG_*                                              */
    int32_t  _pad;   /* keeps the struct 8-byte aligned                        */
} gc_cmd;

/* ------------------------------------------------------------------ */
/* input                                                              */
/* ------------------------------------------------------------------ */

/* Held buttons.  The library edge-detects internally, so pass *held* state. */
#define GC_BTN_DASH    (1u << 0) /* dash / dodge   (space, on-screen button) */
#define GC_BTN_PAUSE   (1u << 1) /* pause menu     (esc)                     */
#define GC_BTN_RESTART (1u << 2) /* restart after game over (R)              */

typedef struct {
    float    move_x, move_y;    /* movement axis, -1..1; the shell may pass a
                                   normalised analogue stick or raw WASD */
    float    aim_x, aim_y;      /* pointer position in VIRTUAL units     */
    int32_t  pointer_active;    /* 1 when a pointer is known (mouse/finger) */
    int32_t  pointer_down;      /* 1 while primary button/finger is held */
    uint32_t buttons;           /* GC_BTN_* bitmask, held state          */
} gc_input;

/* ------------------------------------------------------------------ */
/* events (audio / haptics)                                           */
/* ------------------------------------------------------------------ */

typedef enum {
    GC_EVT_SHOOT       = 1,  /* weapon fired          x,y = muzzle        */
    GC_EVT_HIT         = 2,  /* damage dealt          value = damage      */
    GC_EVT_ENEMY_DIE   = 3,  /* enemy killed          x,y = position      */
    GC_EVT_PLAYER_HURT = 4,  /* player took damage    value = damage      */
    GC_EVT_PICKUP_XP   = 5,  /* xp gem collected      value = amount      */
    GC_EVT_PICKUP_MONEY= 6,  /* money collected       value = amount      */
    GC_EVT_LEVEL_UP    = 7,  /* level up, card picker about to open       */
    GC_EVT_BUY         = 8,  /* shop purchase succeeded value = price     */
    GC_EVT_BUY_FAIL    = 9,  /* shop purchase refused (not enough money)  */
    GC_EVT_WAVE_START  = 10, /* new wave               value = wave index */
    GC_EVT_WAVE_CLEAR  = 11, /* wave cleared, shop opens                  */
    GC_EVT_GAME_OVER   = 12, /* run ended             value = score       */
    GC_EVT_UI_CLICK    = 13, /* a UI element was activated                */
    GC_EVT_DASH        = 14, /* dash used                                 */
    GC_EVT_LIGHTNING   = 15, /* a lightning strike landed                 */
    GC_EVT_CHECKPOINT_PASSED = 16, /* the 10-wave quota was met           */
    GC_EVT_CHECKPOINT_FAILED = 17, /* the quota was missed: run over      */
    GC_EVT_REVIVED     = 18, /* an extra life was spent                 */
    GC_EVT_ENEMY_SHOT  = 19, /* a spitter threw blood  value = damage   */
    GC_EVT_MONEY_STOLEN = 20, /* a miser took coins    value = amount    */
    GC_EVT_BOSS_SPAWN  = 21  /* a boss wave's boss arrived              */
} gc_event_type;

typedef struct {
    int32_t type;  /* gc_event_type */
    float   x, y;  /* virtual units */
    float   value; /* meaning depends on type */
} gc_event;

/* ------------------------------------------------------------------ */
/* status snapshot (window title, save UI, achievements, ...)          */
/* ------------------------------------------------------------------ */

typedef struct {
    int32_t wave;
    int32_t level;
    int32_t kills;
    int32_t money;
    int32_t score;
    int32_t best_score;
    int32_t state;        /* gc_game_state */
    float   player_hp;
    float   player_hp_max;
    float   time_alive;
} gc_status;

typedef enum {
    GC_STATE_TITLE     = 0,
    GC_STATE_PLAYING   = 1,
    GC_STATE_LEVEL_UP  = 2,
    GC_STATE_SHOP      = 3,
    GC_STATE_PAUSED    = 4,
    GC_STATE_GAME_OVER = 5
} gc_game_state;

/* ------------------------------------------------------------------ */
/* UI layout queries                                                  */
/* ------------------------------------------------------------------ */

/* A rectangle in virtual units; (x, y) is the TOP-LEFT corner. */
typedef struct {
    float x, y, w, h;
} gc_rect;

/* The library owns *all* UI layout, including hit testing.  A renderer that
 * wants native buttons (or an automated test that wants to click something)
 * asks for the rectangle instead of hard coding one:
 *
 *   index       clickable slot in the current state: a level-up card, or a shop
 *               entry.  Out of range returns an all-zero rect.
 *   which       0 = primary button (start / resume / play again)
 *               1 = shop "next wave"
 *               2 = pause
 *               3 = shop "previous page" (unused by the tree)
 *               4 = shop "next page"    (unused by the tree)
 *               5..9 = upgrade tree branch tabs
 *
 * Both are in virtual units and match, pixel for pixel, what gc_cmds() draws. */
gc_rect gc_ui_slot(const gc_handle *h, int32_t index);
int32_t gc_ui_slot_count(const gc_handle *h);
gc_rect gc_ui_button(const gc_handle *h, int32_t which);

/* ------------------------------------------------------------------ */
/* upgrade tree queries (additive)                                    */
/* ------------------------------------------------------------------ */

/* The between-round upgrades are a tree of nodes (chains of eight tiers, with
 * keystone nodes gated on a tier in another chain).  The library draws and hit
 * tests it; these calls let a shell or a test find a node on screen. */
int32_t gc_tree_count(void);

/* Index of the backdrop theme currently playing (0..5):
 * HELL, GOLD, LAVA, PARADISE, PURPLE, GODLY.  Renderers use it to choose (and
 * cross-fade) the music track that matches the arena. */
int32_t gc_theme_index(const gc_handle *h);

/* Player settings, for the things only a renderer can do.  Volumes arrive
 * normalised to 0..1 so a shell only has to scale them to its own mixer; the
 * gameplay switches (shake, particles, flashing, aim assist) are already
 * honoured inside the library and are here for completeness. */
typedef struct gc_settings {
    float music;            /* 0..1 */
    float sfx;              /* 0..1 */
    int32_t haptics;        /* 0 or 1 */
    float shake;            /* 0 = off, 1 = default */
    int32_t damage_numbers; /* 0 or 1 */
    int32_t particles;      /* 0 low, 1 medium, 2 high */
    int32_t flashing;       /* 0 full, 1 reduced */
    int32_t aim_assist;     /* 0 or 1 */
    int32_t fullscreen;     /* 0 or 1 */
} gc_settings;

/* Fills *out with the current settings.  Returns 0, or -1 on a bad argument. */
int32_t gc_settings_get(const gc_handle *h, gc_settings *out);

/* 1 while the options screen is open (it overlays the title or pause screen and
 * swallows input). */
int32_t gc_options_open(const gc_handle *h);

/* Opens or closes the options screen from the shell. */
void gc_options_set_open(gc_handle *h, int32_t open);
/* Screen rectangle of a visible node, or an all-zero rect. */
gc_rect gc_tree_rect(const gc_handle *h, int32_t node);
/* 0 = hidden, 1 = locked, 2 = available to buy, 3 = owned. */
int32_t gc_tree_state(const gc_handle *h, int32_t node);
int32_t gc_tree_cost(const gc_handle *h, int32_t node);

/* ------------------------------------------------------------------ */
/* debug hooks (used by the automated screenshot tests)               */
/* ------------------------------------------------------------------ */

typedef enum {
    GC_DBG_GIVE_MONEY    = 1, /* value = amount                    */
    GC_DBG_SET_WAVE      = 2, /* value = wave                      */
    GC_DBG_SKIP_WAVE     = 3, /* kill every enemy on the field     */
    GC_DBG_LEVEL_UP      = 4, /* force the card picker open        */
    GC_DBG_KILL_PLAYER   = 5, /* force game over                   */
    GC_DBG_GIVE_WEAPON   = 6, /* value = gc_weapon_id              */
    GC_DBG_INVULNERABLE  = 7, /* value != 0 disables contact damage*/
    GC_DBG_SET_TIME      = 8, /* value = seconds on the clock      */
    GC_DBG_ADD_EARNED    = 9, /* value = cumulative earnings to add */
    GC_DBG_GRANT_PERK    = 10, /* value = index into the shop's perk list */
    GC_DBG_SPAWN_ENEMY   = 11  /* value = enemy kind index (3 charger, 4
                                  spitter, 5 miser); spawns a few nearby */
} gc_debug_cmd;

/* ------------------------------------------------------------------ */
/* lifecycle                                                          */
/* ------------------------------------------------------------------ */

/* Creates a run.  `seed` makes the whole simulation deterministic. */
gc_handle *gc_create(uint32_t seed);

/* Frees a run.  NULL is ignored. */
void gc_destroy(gc_handle *h);

/* Tells the library the framebuffer size in PIXELS (on mobile: the physical
 * pixel size, not points) plus the safe-area insets in PIXELS.
 * Call once at startup and after every resize / rotation. */
void gc_resize(gc_handle *h, int32_t fb_width, int32_t fb_height,
               float safe_left, float safe_top, float safe_right, float safe_bottom);

/* Virtual size of the current framebuffer (virtual_w = fb_w / scale). */
void gc_virtual_size(const gc_handle *h, float *out_w, float *out_h);

/* Pixels per virtual unit.  Renderers scale their projection by this. */
float gc_view_scale(const gc_handle *h);

/* Advances the simulation.  dt is in seconds and is clamped internally; the
 * library runs its own fixed timestep so variable frame times are fine. */
void gc_update(gc_handle *h, const gc_input *input, float dt);

/* Command list for the frame just simulated, in draw order. */
const gc_cmd *gc_cmds(const gc_handle *h, int32_t *out_count);

/* Events produced by the frame just simulated. */
const gc_event *gc_events(const gc_handle *h, int32_t *out_count);

void gc_status_get(const gc_handle *h, gc_status *out);

/* Incremental progression snapshot.  Additive: renderers that only need the
 * window title can keep using gc_status_get and ignore this. */
typedef struct {
    int32_t tier;         /* completed checkpoints                       */
    int32_t goal;         /* cumulative earnings required at the next one */
    int32_t goal_wave;    /* wave the current goal is checked at          */
    int32_t money_earned; /* total earned this run (the quota metric)     */
} gc_progress;

void gc_progress_get(const gc_handle *h, gc_progress *out);

/* Opaque save blob (best score, settings).  Returns the number of bytes
 * written, or -1 when the buffer is too small / not loadable. */
int32_t gc_save(const gc_handle *h, void *buf, int32_t cap);
int32_t gc_load(gc_handle *h, const void *buf, int32_t len);

/* Test / tooling hooks.  Never required by a shipping renderer. */
void gc_debug(gc_handle *h, int32_t cmd, float value);

/* ------------------------------------------------------------------ */
/* small helpers for renderers (header-only)                          */
/* ------------------------------------------------------------------ */

static inline void gc_pixels_to_virtual(const gc_handle *h, float px, float py,
                                        float *out_x, float *out_y)
{
    float s = gc_view_scale(h);
    if (s <= 0.0f) { s = 1.0f; }
    *out_x = px / s;
    *out_y = py / s;
}

static inline float gc_virtual_to_pixels(const gc_handle *h, float v)
{
    return v * gc_view_scale(h);
}

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* GAME_CORE_H */
