/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef EP5_FILM_PREVIEW_H
#define EP5_FILM_PREVIEW_H
#include "film.h"

/* Both callbacks run on the preview worker. Keep the read lease and private
 * LUT alive until render returns, including after a shutter request. current
 * checks frame/style/card identity and shutter priority. present must check
 * them again atomically with handing off the finished frame. A successful
 * present transfers the destination pixels to the display owner. Neither
 * callback may wait for a shot or own the photograph's LUT/cache. */
struct ep5_preview_sink {
    void *context;
    int (*current)(void *context, uint32_t token);
    int (*present)(void *context, uint32_t token, const struct ep5_image *finished);
};
enum ep5_preview_result {
    EP5_PREVIEW_INVALID = -1, EP5_PREVIEW_DROPPED = 0, EP5_PREVIEW_PRESENTED = 1
};
/* Preview of colour and baked wheel only. Caller supplies matching-size,
 * non-overlapping source and backstage buffers and a nonzero generation.
 * Only 'present' can publish. Input is never modified. No file or camera I/O.
 * At zero strength pass NULL,0 for the LUT or supply the usual table. */
int ep5_preview_render(const struct ep5_image *source, struct ep5_image *backstage,
                       const uint16_t *table, size_t values, unsigned encoding,
                       unsigned amount, uint32_t token, const struct ep5_preview_sink *sink);
#endif
