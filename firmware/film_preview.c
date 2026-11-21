/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "film_preview.h"

static size_t span(const struct ep5_image *image)
{
    if (!image || !image->data || !image->width || (image->width & 1u) || !image->height)
        return 0;
    size_t row = (size_t)image->width * 2u;
    if (row / 2u != image->width || image->stride < row ||
        image->height - 1u > (SIZE_MAX - row) / image->stride)
        return 0;
    size_t used = (size_t)(image->height - 1u) * image->stride + row;
    if (used > image->capacity || used - 1u > UINTPTR_MAX - (uintptr_t)image->data)
        return 0;
    return used;
}

static int overlaps(const void *a, size_t na, const void *b, size_t nb)
{
    uintptr_t aa = (uintptr_t)a, bb = (uintptr_t)b;
    return aa <= bb ? bb - aa < na : aa - bb < nb;
}

int ep5_preview_render(const struct ep5_image *source, struct ep5_image *backstage,
                       const uint16_t *table, size_t values, unsigned encoding,
                       unsigned amount, uint32_t token, const struct ep5_preview_sink *sink)
{
    size_t src_size = span(source), dst_size = span(backstage);
    if (!src_size || !dst_size || source->width != backstage->width ||
        source->height != backstage->height || encoding != EP5_BT601_FULL_YUYV ||
        amount > 256 || !token || !sink || !sink->current || !sink->present ||
        overlaps(source->data, src_size, backstage->data, dst_size))
        return EP5_PREVIEW_INVALID;
    if (table) {
        if (values != EP5_LUT_VALUES || ((uintptr_t)table & 1u) ||
            values * sizeof(*table) - 1u > UINTPTR_MAX - (uintptr_t)table ||
            overlaps(table, values * sizeof(*table), backstage->data, dst_size))
            return EP5_PREVIEW_INVALID;
    } else if (amount || values) {
        return EP5_PREVIEW_INVALID;
    }
    size_t row_size = (size_t)source->width * 2u;
    for (uint32_t y = 0; y < source->height; ++y) {
        if (!sink->current(sink->context, token)) return EP5_PREVIEW_DROPPED;
        const uint8_t *src = source->data + (size_t)y * source->stride;
        uint8_t *dst = backstage->data + (size_t)y * backstage->stride;
        for (size_t i = 0; i < row_size; ++i) dst[i] = src[i];
        if (amount) {
            struct ep5_image row = {dst, row_size, source->width, 1, row_size};
            if (ep5_film_apply(&row, table, values, encoding, amount, NULL, NULL))
                return EP5_PREVIEW_INVALID;
        }
    }
    return sink->present(sink->context, token, backstage) ? EP5_PREVIEW_PRESENTED : EP5_PREVIEW_DROPPED;
}
