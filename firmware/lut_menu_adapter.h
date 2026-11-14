#ifndef EP5_LUT_MENU_ADAPTER_H
#define EP5_LUT_MENU_ADAPTER_H

#include "lut_menu.h"

int ep5_lut_menu_stock_event(struct ep5_lut_menu *menu, uint16_t event);
unsigned ep5_lut_menu_display(const volatile struct ep5_lut_menu *menu,
                              struct ep5_lut_menu_line *lines, unsigned capacity);

#endif
