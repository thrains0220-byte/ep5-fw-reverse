/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Exercise the capture task in the existing MN103 CPU model. All addresses
 * below belong to lut_mn103_probe's synthetic memories. */
#include "film_shot.h"
#include "object_bytes.h"

enum scenario { CHANGE_CARD, CANCEL_SHUTTER, DENY_CLAIM, FAIL_SUBMIT };
struct frame_owner {
    uint32_t token, scenario;
    unsigned claims, submits, discards;
};
extern void ep5_probe_done(void);

static void noop(void *ctx) { (void)ctx; }

static int claim(void *ctx, uint32_t token, struct ep5_image *out, unsigned *encoding)
{
    struct frame_owner *owner = ctx;
    ++owner->claims;
    if (token != owner->token || owner->scenario == DENY_CLAIM) return 0;
    *out = (struct ep5_image){(uint8_t *)0x12000010u, 12, 2, 2, 8};
    *encoding = EP5_BT601_FULL_YUYV;
    return 1;
}

static int submit(void *ctx, uint32_t token, int result)
{
    struct frame_owner *owner = ctx;
    ++owner->submits;
    return token == owner->token && result == EP5_PHOTO_STYLED && owner->scenario != FAIL_SUBMIT;
}

static void discard(void *ctx, uint32_t token)
{
    struct frame_owner *owner = ctx;
    if (token == owner->token) ++owner->discards;
}

__attribute__((section(".text.probe")))
void ep5_probe(void)
{
    const uint16_t *black = (const uint16_t *)0x13000000u;
    struct frame_owner owner = {.scenario = *(volatile const uint32_t *)0x11000000u};
    struct ep5_camera_choice choice;
    ep5_zero_bytes(&choice, sizeof choice);
    choice.mount = 5;
    choice.bank = 2;
    choice.revision = 21;
    choice.look = (struct ep5_lut_menu_capture){
        .picture_mode = 101, .variant = 1, .amount_q8 = 256, .number = 1, .look_crc = 3};
    struct ep5_shot_recipe recipe;
    ep5_zero_bytes(&recipe, sizeof recipe);
    recipe.mount = choice.mount;
    recipe.bank = choice.bank;
    recipe.revision = choice.revision;
    recipe.medium = 6;
    recipe.look = choice.look;
    struct ep5_lut_preload cache;
    ep5_zero_bytes(&cache, sizeof cache);
    cache.sync = (struct ep5_lut_preload_sync){0, noop, noop};
    cache.medium = recipe.medium;
    cache.published = (struct ep5_look_selection){black, 256, 1, 3};
    cache.desired = choice.look;
    struct ep5_capture_sequence sequence;
    ep5_zero_bytes(&sequence, sizeof sequence);
    struct ep5_capture_backend backend = {&owner, claim, submit, discard};
    owner.token = ep5_capture_begin(&sequence, &cache, 2, 2, &recipe, &choice);
    unsigned ok = owner.token && cache.pinned == black;
    ep5_lut_preload_media(&cache, 7);
    if (owner.scenario == CANCEL_SHUTTER)
        ok &= ep5_capture_cancel_pending(&sequence, owner.token) == 1;
    int result = ep5_capture_ready(&sequence, owner.token, &backend, 0, 0, 0);
    ok &= ep5_capture_ready(&sequence, owner.token, &backend, 0, 0, 0) == EP5_CAPTURE_IGNORED;
    ok &= !cache.pinned && !cache.shot;
    /* Return the actual outcomes to the host's independent oracle. */
    *(volatile uint32_t *)0x1100001cu = (ok << 24) | (owner.claims << 20) |
        (owner.submits << 16) | (owner.discards << 12) | ((uint32_t)result & 0xffu);
    ep5_probe_done();
}
