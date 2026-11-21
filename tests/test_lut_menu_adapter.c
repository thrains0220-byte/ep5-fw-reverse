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
    /* A key repeat delivered after closing must not clear the shot selection. */
    assert(ep5_lut_menu_stock_event(&menu, 0x9016) == 0 && menu.applied == 2);

    struct ep5_look_page page;
    memset(slots, 0, sizeof slots);
    for (unsigned i = 1; i <= 13; i += 3) {
        slots[i].configured = 1;
        slots[i].label[0] = (uint16_t)('A' + i);
        slots[i].amount_q8 = 128;
    }
    assert(ep5_lut_menu_begin_load(&menu, 10));
    assert(ep5_lut_menu_publish(&menu, 10, slots));
    assert(ep5_lut_menu_page(&menu, &page));
    assert(page.total == 5 && page.first == 0 && page.count == 4);
    assert(page.rows[0].name[0] == 'B' && page.rows[0].focused);
    assert(ep5_lut_menu_stock_event(&menu, 0x9012) == 2);
    assert(ep5_lut_menu_stock_event(&menu, 0x9006) == 1);
    assert(ep5_lut_menu_page(&menu, &page));
    assert(page.rows[0].confirmed && !page.rows[0].focused);
    assert(page.rows[1].focused && !page.rows[1].confirmed);
    assert(ep5_lut_menu_stock_event(&menu, 0x9004) == 1);
    assert(ep5_lut_menu_stock_event(&menu, 0x9004) == 1);
    assert(ep5_lut_menu_stock_event(&menu, 0x900a) == 1);
    assert(ep5_lut_menu_page(&menu, &page));
    assert(page.first == 4 && page.count == 1 && page.rows[0].name[0] == 'N');
    assert(page.rows[0].focused && !page.rows[0].confirmed && page.rows[0].percent == 56);
    assert(page.rows[1].name[0] == 0);
    /* Text for an in-flight draw survives a card change in a different object. */
    assert(ep5_lut_menu_begin_load(&menu, 11));
    assert(page.rows[0].name[0] == 'N');
    assert(ep5_lut_menu_page(&menu, &page));
    assert(page.state == EP5_LUT_MENU_LOADING && !page.total && !page.rows[0].name[0]);
    memset(slots, 0, sizeof slots);
    assert(ep5_lut_menu_publish(&menu, 11, slots));
    assert(ep5_lut_menu_page(&menu, &page) && page.state == EP5_LUT_MENU_READY && !page.count);
    assert(ep5_lut_menu_stock_event(&menu, 0x9006) == 1 && menu.cursor == 0);
    assert(ep5_lut_menu_stock_event(&menu, 0x900a) == 1 && menu.amount_q8 == 0);

    slots[11].configured = 1;
    slots[11].amount_q8 = 128;
    assert(ep5_lut_menu_begin_load(&menu, 12));
    assert(ep5_lut_menu_publish(&menu, 12, slots));
    assert(ep5_lut_menu_stock_event(&menu, 0x900a) == 1);
    assert(ep5_lut_menu_stock_event(&menu, 0x9004) == 1);
    assert(menu.cursor == 11 && menu.amount_q8 == 144);
    assert(ep5_lut_menu_stock_event(&menu, 0x9014) == 3);
    assert(!ep5_lut_menu_page(&menu, &page) && !page.count && !page.rows[0].name[0]);
    return 0;
}
