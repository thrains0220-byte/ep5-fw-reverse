#ifndef EP5_LUT_MENU_ADAPTER_H
#define EP5_LUT_MENU_ADAPTER_H

#include "lut_menu.h"

int ep5_lut_menu_stock_event(struct ep5_lut_menu *menu, uint16_t event);
unsigned ep5_lut_menu_display(const volatile struct ep5_lut_menu *menu,
                              struct ep5_lut_menu_line *lines, unsigned capacity);

/* A compact, pointer-free copy owned by the caller until drawing completes.
 * Build and consume on a serialized UI task. Four rows is our layout choice. */
#define EP5_LOOK_PAGE_ROWS 4u
struct ep5_look_page_row {
    uint16_t name[EP5_LUT_MENU_LABEL_UNITS];
    uint8_t focused;
    uint8_t confirmed;
    uint8_t percent;
};
struct ep5_look_page {
    uint8_t state;
    uint8_t total;
    uint8_t first; /* zero-based ordinal among configured looks */
    uint8_t count;
    struct ep5_look_page_row rows[EP5_LOOK_PAGE_ROWS];
};
int ep5_lut_menu_page(const struct ep5_lut_menu *menu, struct ep5_look_page *page);

#endif
