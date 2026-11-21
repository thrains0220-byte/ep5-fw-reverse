#include "film_preview.h"
#include "film_photo.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>

struct display {
    uint32_t token, checks, stop_at, presented;
    int shutter_at_swap;
};
static int current(void *ctx, uint32_t token)
{
    struct display *d = ctx;
    return d->token == token && ++d->checks != d->stop_at;
}
static int present(void *ctx, uint32_t token, const struct ep5_image *finished)
{
    struct display *d = ctx;
    assert(finished->data);
    if (token != d->token || d->shutter_at_swap) return 0;
    ++d->presented;
    return 1;
}
static void noop(void *ctx) { (void)ctx; }

static void exercise(unsigned width, unsigned height, unsigned amount)
{
    static uint16_t photo_lut[EP5_LUT_VALUES], preview_lut[EP5_LUT_VALUES];
    for (size_t i = 0; i < EP5_LUT_VALUES; ++i)
        photo_lut[i] = preview_lut[i] = (uint16_t)(i * 71u + 255u);
    size_t row = 2u * width;
    size_t src_pitch = row + 8u, dst_pitch = row + 16u;
    size_t src_bytes = src_pitch * height, dst_bytes = dst_pitch * height;
    uint8_t *input = malloc(src_bytes), *reference = malloc(src_bytes);
    uint8_t *pixels = malloc(dst_bytes), *expected = malloc(dst_bytes);
    assert(input && reference && pixels && expected);
    for (size_t i = 0; i < src_bytes; ++i) input[i] = (uint8_t)(i * 11u ^ (i >> 7));
    memcpy(reference, input, src_bytes);
    memset(pixels, 0xc7, dst_bytes);
    memset(expected, 0xc7, dst_bytes);
    for (size_t y = 0; y < height; ++y)
        memcpy(expected + y * dst_pitch, input + y * src_pitch, row);

    struct ep5_image src = {input, src_bytes, width, height, src_pitch};
    struct ep5_image dst = {pixels, dst_bytes, width, height, dst_pitch};
    struct ep5_image photo = {expected, dst_bytes, width, height, dst_pitch};
    struct ep5_photo_style style = {.medium=27, .choice={105,1,amount,2,0x988u}};
    struct ep5_lut_preload loader = {.sync={NULL,noop,noop}, .medium=27,
        .desired=style.choice, .published={photo_lut,amount,2,0x988u}};
    struct display state = {.token=8};
    struct ep5_preview_sink sink = {&state, current, present};
    /* A real shot owns the photograph's LUT while the preview is running. */
    struct ep5_look_selection pin;
    assert(ep5_lut_preload_acquire(&loader, 27, 40, &style.choice, &pin));
    assert(ep5_preview_render(&src,&dst,preview_lut,EP5_LUT_VALUES,EP5_BT601_FULL_YUYV,
                              amount,8,&sink) == EP5_PREVIEW_PRESENTED);
    assert(state.presented == 1 && loader.shot == 40 && loader.pinned == photo_lut);
    assert(ep5_lut_preload_release(&loader,40));
    assert(ep5_photo_render(&loader, 41, &style, &photo, EP5_BT601_FULL_YUYV, NULL, NULL, NULL)
           == (amount ? EP5_PHOTO_STYLED : EP5_PHOTO_STOCK));
    assert(memcmp(expected, pixels, dst_bytes) == 0 && memcmp(input, reference, src_bytes) == 0);

    memset(pixels, 0xa9, dst_bytes);
    state = (struct display){.token=9};
    assert(ep5_preview_render(&src,&dst,preview_lut,EP5_LUT_VALUES,EP5_BT601_FULL_YUYV,
                              amount,8,&sink) == EP5_PREVIEW_DROPPED);
    for (size_t i = 0; i < dst_bytes; ++i) assert(pixels[i] == 0xa9);
    state = (struct display){.token=8,.stop_at=3};
    assert(ep5_preview_render(&src,&dst,preview_lut,EP5_LUT_VALUES,EP5_BT601_FULL_YUYV,
                              amount,8,&sink) == EP5_PREVIEW_DROPPED);
    assert(state.checks == 3 && state.presented == 0);
    for (size_t i = 2u*dst_pitch; i < dst_bytes; ++i) assert(pixels[i] == 0xa9);
    state = (struct display){.token=8,.shutter_at_swap=1};
    assert(ep5_preview_render(&src,&dst,preview_lut,EP5_LUT_VALUES,EP5_BT601_FULL_YUYV,
                              amount,8,&sink) == EP5_PREVIEW_DROPPED);
    assert(state.checks == height && state.presented == 0);
    struct ep5_image alias = src;
    ++alias.data; --alias.capacity;
    assert(ep5_preview_render(&src,&alias,preview_lut,EP5_LUT_VALUES,EP5_BT601_FULL_YUYV,
                              amount,8,&sink) == EP5_PREVIEW_INVALID);
    assert(ep5_preview_render(&src,&dst,(const uint16_t *)dst.data,EP5_LUT_VALUES,EP5_BT601_FULL_YUYV,
                              amount,8,&sink) == EP5_PREVIEW_INVALID);
    dst.capacity = row - 1;
    assert(ep5_preview_render(&src,&dst,preview_lut,EP5_LUT_VALUES,EP5_BT601_FULL_YUYV,
                              amount,8,&sink) == EP5_PREVIEW_INVALID);
    assert(memcmp(input, reference, src_bytes) == 0);
    free(input); free(reference); free(pixels); free(expected);
}
int main(void)
{
    exercise(320,240,0);
    exercise(320,240,256);
    exercise(640,480,192);
    exercise(720,480,256);
    return 0;
}
