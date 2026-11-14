#include "lut_menu_adapter.h"

int ep5_lut_menu_stock_event(struct ep5_lut_menu *menu, uint16_t event)
{
    switch (event) {
    case 0x9004: return ep5_lut_menu_event(menu, EP5_LUT_MENU_UP);
    case 0x9006: return ep5_lut_menu_event(menu, EP5_LUT_MENU_DOWN);
    case 0x9008: return ep5_lut_menu_event(menu, EP5_LUT_MENU_LEFT);
    case 0x900a: return ep5_lut_menu_event(menu, EP5_LUT_MENU_RIGHT);
    case 0x900c:
    case 0x900e:
    case 0x9012: return ep5_lut_menu_event(menu, EP5_LUT_MENU_OK);
    case 0x9014:
    case 0x9016: return ep5_lut_menu_event(menu, EP5_LUT_MENU_BACK);
    default: return 0;
    }
}

unsigned ep5_lut_menu_display(const volatile struct ep5_lut_menu *menu,
                              struct ep5_lut_menu_line *lines, unsigned capacity)
{ return ep5_lut_menu_lines(menu, lines, capacity); }
