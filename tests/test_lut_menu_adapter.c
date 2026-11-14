#include <assert.h>
#include <string.h>
#include "lut_menu_adapter.h"

int main(void)
{
    struct ep5_lut_menu menu;
    struct ep5_lut_menu_slot slots[EP5_LUT_MENU_SLOTS];
    struct ep5_lut_menu_line lines[EP5_LUT_MENU_LINE_COUNT];
    ep5_lut_menu_init(&menu);
    for (unsigned index = 0; index < EP5_LUT_MENU_SLOTS; ++index) {
        memset(&slots[index], 0, sizeof slots[index]);
        slots[index].configured = 1;
        slots[index].picture_mode = 105;
        slots[index].variant = (uint8_t)(index + 1);
        slots[index].amount_q8 = (uint16_t)(128 + index);
        slots[index].label[0] = (uint16_t)('A' + index);
    }
    assert(ep5_lut_menu_begin_load(&menu, 1));
    assert(ep5_lut_menu_publish(&menu, 1, slots));
    assert(ep5_lut_menu_stock_event(&menu, 0x9006) == 1 && menu.cursor == 1);
    assert(ep5_lut_menu_stock_event(&menu, 0x9008) == 1 && menu.amount_q8 == 113);
    assert(ep5_lut_menu_stock_event(&menu, 0x900a) == 1 && menu.amount_q8 == 129);
    assert(ep5_lut_menu_stock_event(&menu, 0x900c) == 2 && menu.applied == 2);
    assert(ep5_lut_menu_display(&menu, lines, EP5_LUT_MENU_LINE_COUNT) == EP5_LUT_MENU_LINE_COUNT);
    assert(lines[0].kind == EP5_LUT_MENU_LINE_TITLE && lines[2].selected);
    assert(ep5_lut_menu_stock_event(&menu, 0x9014) == 3);
    assert(menu.state == EP5_LUT_MENU_HIDDEN);
    assert(ep5_lut_menu_stock_event(&menu, 0xdead) == 0);
    return 0;
}
