#ifndef EP5_LUT_WHEEL_DRAW_H
#define EP5_LUT_WHEEL_DRAW_H
#include "lut_wheel_view.h"

/* Coordinates in native menu font cells. A half-width glyph occupies one
 * column and a CJK character occupies two. Text is borrowed only for the call.
 * The GUI supplies its existing font and maps RGB24 to its active palette. */
struct ep5_wheel_surface {
    void *ctx;
    unsigned columns, rows;
    void (*fill)(void *ctx, unsigned x, unsigned y, unsigned width, unsigned height, uint32_t rgb);
    void (*text)(void *ctx, unsigned x, unsigned y, const uint16_t *text, uint32_t rgb);
};
int ep5_wheel_draw(const struct ep5_wheel_editor *editor, const struct ep5_lut_menu *menu,
                   uint32_t mount, const struct ep5_wheel_surface *surface);
#endif
