/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "film_photo.h"
#include "object_bytes.h"

struct photo_progress {
    int (*callback)(void *, uint32_t, uint32_t);
    void *context;
    uint32_t offset, total;
};

static int report_rows(void *context, uint32_t done, uint32_t height)
{
    struct photo_progress *p = context;
    (void)height;
    return p->callback(p->context, p->offset + done, p->total);
}

static int wheel_applies(const struct ep5_photo_style *style)
{
    const struct ep5_wheel_edit *w = style->wheel;
    return w && style->wheel_medium == style->medium &&
           w->picture_mode == style->choice.picture_mode && w->variant == style->choice.variant &&
           w->number == style->choice.number && w->look_crc == style->choice.look_crc;
}

int ep5_photo_render_pinned(const struct ep5_look_selection *look,
                            const struct ep5_photo_style *style, const struct ep5_image *image,
                            unsigned encoding, const struct ep5_photo_workspace *workspace,
                            int (*progress)(void *, uint32_t, uint32_t), void *context)
{
    struct ep5_film_fx_settings fx;
    if (!look || !look->table || !style || !ep5_image_valid(image) || encoding != EP5_BT601_FULL_YUYV ||
        !look->amount_q8 || look->amount_q8 > 256 || look->amount_q8 != style->choice.amount_q8 ||
        look->number != style->choice.number || look->look_crc != style->choice.look_crc)
        return EP5_PHOTO_INVALID;
    ep5_copy_bytes(&fx, &style->fx, sizeof fx);
    if (fx.grain > 100 || fx.halation > 100 || fx.bloom > 100 || fx.clarity > 100 ||
        fx.halo_tint > EP5_FILM_HALO_RED) return EP5_PHOTO_INVALID;
    /* From here to the LUT pass the capture buffer is still untouched. If
     * this style cannot fit this shot, the encoder can use the stock frame. */
    fx.grain = (fx.grain * look->amount_q8 + 128u) / 256u;
    fx.halation = (fx.halation * look->amount_q8 + 128u) / 256u;
    fx.bloom = (fx.bloom * look->amount_q8 + 128u) / 256u;
    fx.clarity = (fx.clarity * look->amount_q8 + 128u) / 256u;
    int use_fx = fx.grain || fx.halation || fx.bloom || fx.clarity;
    size_t bytes = ep5_film_fx_scratch_bytes(image->width, &fx);
    if ((fx.halation || fx.bloom || fx.clarity) && !bytes) return EP5_PHOTO_STOCK;
    if (bytes && (!workspace || !workspace->fx_scratch || workspace->fx_bytes < bytes)) return EP5_PHOTO_STOCK;
    if (use_fx && image->height > UINT32_MAX / 2u) return EP5_PHOTO_STOCK;

    const uint16_t *table = look->table;
    if (wheel_applies(style)) {
        if (!workspace || !workspace->wheel_table || workspace->wheel_table == table ||
            workspace->wheel_words < EP5_LUT_VALUES ||
            !ep5_wheel_bake(&style->wheel->values, table, EP5_LUT_VALUES,
                            workspace->wheel_table, workspace->wheel_words, 0, EP5_WHEEL_NODES))
            return EP5_PHOTO_STOCK;
        table = workspace->wheel_table;
    }
    struct photo_progress rows = {progress, context, 0, image->height * (use_fx ? 2u : 1u)};
    int result = ep5_film_apply(image, table, EP5_LUT_VALUES, encoding, look->amount_q8,
                                progress ? report_rows : NULL, &rows);
    if (result != 0) return result;
    if (use_fx) {
        rows.offset = image->height;
        result = ep5_film_fx_apply(image, encoding, &fx, workspace ? workspace->fx_scratch : NULL,
                                   bytes, progress ? report_rows : NULL, &rows);
        /* Even if FX cancels before its first row the LUT pass has written. */
        if (result != 0) return EP5_PHOTO_DISCARD;
    }
    return EP5_PHOTO_STYLED;
}

int ep5_photo_render(struct ep5_lut_preload *loader, uint32_t shot,
                     const struct ep5_photo_style *style, const struct ep5_image *image,
                     unsigned encoding, const struct ep5_photo_workspace *workspace,
                     int (*progress)(void *, uint32_t, uint32_t), void *context)
{
    struct ep5_look_selection look;
    if (!loader || !style || !shot || !ep5_image_valid(image) ||
        encoding != EP5_BT601_FULL_YUYV || style->choice.amount_q8 > 256)
        return EP5_PHOTO_INVALID;
    if (!style->choice.amount_q8 ||
        !ep5_lut_preload_acquire(loader, style->medium, shot, &style->choice, &look))
        return EP5_PHOTO_STOCK;
    int result = ep5_photo_render_pinned(&look, style, image, encoding, workspace, progress, context);
    if (!ep5_lut_preload_release(loader, shot)) return EP5_PHOTO_DISCARD;
    return result;
}
