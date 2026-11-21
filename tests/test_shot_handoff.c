#include <assert.h>
#include <string.h>
#include "film_shot.h"

static void noop(void *ctx) { (void)ctx; }
static uint16_t black[EP5_LUT_VALUES];

struct fixture {
    struct ep5_image image;
    unsigned encoding, claims, submissions, discards;
    int available, can_submit;
    uint32_t lease;
};
static int claim(void *ctx, uint32_t shot, struct ep5_image *image, unsigned *encoding)
{
    struct fixture *f = ctx;
    ++f->claims;
    assert(!f->lease);
    if (!f->available) return 0;
    f->lease = shot;
    *image = f->image;
    *encoding = f->encoding;
    return 1;
}
static int submit(void *ctx, uint32_t shot, int result)
{
    struct fixture *f = ctx;
    assert(f->lease == shot && (result == EP5_PHOTO_STOCK || result == EP5_PHOTO_STYLED));
    if (!f->can_submit) return 0;
    ++f->submissions;
    f->lease = 0;
    return 1;
}
static void discard(void *ctx, uint32_t shot)
{
    struct fixture *f = ctx;
    assert(f->lease == shot);
    f->lease = 0;
    ++f->discards;
}

static void test_frame_ownership(struct ep5_lut_preload *cache, struct ep5_shot_recipe *recipe,
                                 struct ep5_camera_choice *active)
{
    uint8_t src[] = {180,128,180,128};
    struct ep5_capture_sequence state = {0};
    struct fixture f = {.image = {src, sizeof src, 2, 1, 4}, .encoding = EP5_BT601_FULL_YUYV,
                        .available = 1, .can_submit = 1};
    struct ep5_capture_backend io = {&f, claim, submit, discard};
    uint32_t old = ep5_capture_begin(&state, cache, 2, 1, recipe, active);
    assert(old && !ep5_capture_begin(&state, cache, 2, 1, recipe, active));
    assert(cache->pinned == black && ep5_capture_cancel_pending(&state, old) && !cache->pinned);
    uint32_t next = ep5_capture_begin(&state, cache, 2, 1, recipe, active);
    assert(next && next != old && !ep5_capture_cancel_pending(&state, old));
    ++active->revision; /* user selects a different look before producer completes */
    /* The UI updates the actual preload selection and invalidates its
     * publication on unmount. The outstanding shutter still owns its table. */
    struct ep5_look_selection previous = cache->published;
    struct ep5_lut_menu_capture different = active->look;
    ++different.number;
    assert(ep5_lut_preload_select(cache, recipe->medium, &different) && !cache->published.table);
    ep5_lut_preload_media(cache, 0);
    assert(ep5_capture_ready(&state, old, &io, NULL, NULL, NULL) == EP5_CAPTURE_IGNORED);
    assert(!f.claims && src[0] == 180 && cache->pinned == black && cache->shot == next);
    assert(ep5_capture_ready(&state, next, &io, NULL, NULL, NULL) == EP5_PHOTO_STYLED);
    assert(f.submissions == 1 && !f.discards && !f.lease && src[0] == 0);
    assert(ep5_capture_ready(&state, next, &io, NULL, NULL, NULL) == EP5_CAPTURE_IGNORED);
    assert(f.claims == 1 && f.submissions == 1 && !cache->pinned);
    --active->revision;
    src[0] = 222;
    /* Newly mounted card has no table at shutter, even if its file task
     * publishes a matching table before completion. */
    ep5_lut_preload_media(cache, recipe->medium + 1);
    ++recipe->medium;
    next = ep5_capture_begin(&state, cache, 2, 1, recipe, active);
    assert(next && !cache->pinned);
    assert(ep5_lut_preload_select(cache, recipe->medium, &active->look));
    cache->published = previous;
    assert(ep5_capture_ready(&state, next, &io, NULL, NULL, NULL) == EP5_PHOTO_STOCK);
    assert(src[0] == 222 && f.submissions == 2 && !cache->pinned);
    f.encoding = 0;
    next = ep5_capture_begin(&state, cache, 2, 1, recipe, active);
    assert(ep5_capture_ready(&state, next, &io, NULL, NULL, NULL) == EP5_PHOTO_STOCK);
    assert(src[0] == 222 && f.submissions == 3 && !cache->pinned);
    next = ep5_capture_begin(&state, cache, 4608, 3456, recipe, active);
    assert(ep5_capture_ready(&state, next, &io, NULL, NULL, NULL) == EP5_PHOTO_INVALID);
    assert(f.discards == 1 && !f.lease && f.submissions == 3 && src[0] == 222 && !cache->pinned);
    f.encoding = EP5_BT601_FULL_YUYV;
    f.can_submit = 0;
    next = ep5_capture_begin(&state, cache, 2, 1, recipe, active);
    assert(ep5_capture_ready(&state, next, &io, NULL, NULL, NULL) == EP5_PHOTO_DISCARD);
    assert(f.discards == 2 && !f.lease && f.submissions == 3 && !cache->pinned);
    f.available = 0;
    next = ep5_capture_begin(&state, cache, 2, 1, recipe, active);
    assert(ep5_capture_ready(&state, next, &io, NULL, NULL, NULL) == EP5_CAPTURE_BYPASS);
    assert(f.discards == 2 && !f.lease && f.submissions == 3 && !cache->pinned);
    next = ep5_capture_begin(&state, cache, 2, 1, recipe, active);
    assert(cache->pinned == black);
    assert(ep5_capture_ready(&state, next, NULL, NULL, NULL, NULL) == EP5_CAPTURE_BYPASS && !cache->pinned);
    state.last=UINT32_MAX;
    assert(!ep5_capture_begin(&state, cache, 2, 1, recipe, active));
}

int main(void)
{
    /* Both groups deliberately have the same slot, number and table CRC. */
    struct ep5_camera_choice active = {.mount = 41, .revision = 132, .bank = 2,
        .look = {.picture_mode = 101, .variant = 1, .amount_q8 = 256, .number = 1, .look_crc = 3}};
    struct ep5_lut_preload cache = {.sync = {NULL, noop, noop}, .medium = 62,
        .desired = active.look, .published = {black, 256, 1, 3}};
    struct ep5_shot_recipe recipe;
    assert(ep5_shot_prepare(&recipe, &active, NULL, 62, 0) == 0);
    uint8_t src[] = {170,128,200,128};
    struct ep5_image image = {src, sizeof src, 2, 1, 4};
    for (unsigned i = 0; i < 3; ++i) {
        struct ep5_camera_choice changed = active;
        if (i == 0) ++changed.bank;
        if (i == 1) ++changed.mount;
        if (i == 2) ++changed.revision;
        assert(ep5_shot_develop(&cache, 45, &recipe, &changed, &image, EP5_BT601_FULL_YUYV,
                                NULL, NULL, NULL) == EP5_PHOTO_STOCK);
        assert(!memcmp(src, (uint8_t[]){170,128,200,128}, sizeof src));
    }
    /* A failed scratch allocation must not lose a valid stock picture. */
    recipe.fx.halation=70;
    assert(ep5_shot_develop(&cache, 45, &recipe, &active, &image, EP5_BT601_FULL_YUYV,
                            NULL, NULL, NULL) == EP5_PHOTO_STOCK && !cache.pinned);
    recipe.fx.halation=0;
    active.has_wheel=1;
    assert(ep5_shot_develop(&cache, 45, &recipe, &active, &image, EP5_BT601_FULL_YUYV,
                            NULL, NULL, NULL) == EP5_PHOTO_STOCK && !cache.pinned);
    assert(!memcmp(src, (uint8_t[]){170,128,200,128}, sizeof src));
    active.has_wheel=0;
    assert(ep5_shot_develop(&cache, 46, &recipe, &active, &image, EP5_BT601_FULL_YUYV,
                            NULL, NULL, NULL) == EP5_PHOTO_STYLED);
    assert(!memcmp(src, (uint8_t[]){0,128,0,128}, sizeof src) && !cache.pinned);
    image.capacity--;
    assert(ep5_shot_develop(&cache, 47, NULL, NULL, &image, EP5_BT601_FULL_YUYV,
                            NULL, NULL, NULL) == EP5_PHOTO_INVALID);
    test_frame_ownership(&cache, &recipe, &active);
    return 0;
}
