/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef EP5_FILM_PHOTO_H
#define EP5_FILM_PHOTO_H
#include "film_fx.h"
#include "lut_preload.h"
#include "lut_wheel.h"

struct ep5_photo_style {
    /* Snapshot on the same serialized UI context as the selection. A mount
     * token identifies a card/bank, not a slot number or a filename. */
    uint32_t medium;
    struct ep5_lut_menu_capture choice;
    const struct ep5_wheel_edit *wheel;
    uint32_t wheel_medium;
    struct ep5_film_fx_settings fx;
};
struct ep5_photo_workspace {
    uint16_t *wheel_table;
    size_t wheel_words;
    void *fx_scratch;
    size_t fx_bytes;
};
enum ep5_photo_result {
    EP5_PHOTO_STOCK = 0, EP5_PHOTO_STYLED = 1,
    EP5_PHOTO_INVALID = EP5_FILM_INVALID, EP5_PHOTO_CANCELLED = EP5_FILM_CANCELLED,
    EP5_PHOTO_DISCARD = EP5_FILM_DISCARD
};
/* Process an exclusively owned, already-developed image. STOCK leaves it
 * untouched; only STOCK/STYLED permit encoding. No file or card I/O. NULL
 * workspace is valid without wheel edits or spatial scratch. A shortage of
 * optional workspace before any image writes yields STOCK. All buffers
 * must be disjoint. Keep the snapshot, edit and workspace private to this shot.
 * The progress callback can cancel and receives a monotonically increasing
 * row count over all enabled passes. */
int ep5_photo_render(struct ep5_lut_preload *loader, uint32_t shot,
                     const struct ep5_photo_style *style, const struct ep5_image *image,
                     unsigned encoding, const struct ep5_photo_workspace *workspace,
                     int (*progress)(void *, uint32_t, uint32_t), void *context);
/* Render with a selection already acquired for this shot. The caller owns
 * its pin throughout this function and releases it on every exit. */
int ep5_photo_render_pinned(const struct ep5_look_selection *look,
                            const struct ep5_photo_style *style, const struct ep5_image *image,
                            unsigned encoding, const struct ep5_photo_workspace *workspace,
                            int (*progress)(void *, uint32_t, uint32_t), void *context);
#endif
