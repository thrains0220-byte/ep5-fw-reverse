#include <assert.h>
#include <string.h>
#include "film_shot.h"

static void noop(void *ctx) { (void)ctx; }
static uint16_t black[EP5_LUT_VALUES];

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
    return 0;
}
