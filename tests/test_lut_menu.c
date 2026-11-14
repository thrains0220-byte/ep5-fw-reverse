#include <assert.h>
#include <string.h>
#include "lut_menu.h"
#include "lut_menu_index.h"

static void slot(struct ep5_lut_menu_slot *value, unsigned number, unsigned amount)
{
    memset(value, 0, sizeof *value);
    value->configured = 1;
    value->number = (uint16_t)number;
    value->amount_q8 = (uint16_t)amount;
    value->label[0] = (uint16_t)('A' + number);
}

int main(void)
{
    struct ep5_lut_menu menu;
    struct ep5_lut_menu_slot slots[EP5_LUT_MENU_SLOTS];
    ep5_lut_menu_init(&menu);
    assert(menu.state == EP5_LUT_MENU_HIDDEN && menu.applied == 0);
    assert(ep5_lut_menu_begin_load(&menu, 1) == 1);
    assert(ep5_lut_menu_begin_load(&menu, 2) == 1);
    slot(&slots[0], 1, 128); slot(&slots[1], 2, 192); slot(&slots[2], 3, 256);
    assert(ep5_lut_menu_publish(&menu, 1, slots) == 0);
    assert(ep5_lut_menu_publish(&menu, 2, slots) == 1);
    assert(menu.state == EP5_LUT_MENU_READY && menu.amount_q8 == 128);
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_DOWN) == 1);
    assert(menu.cursor == 1 && menu.amount_q8 == 192);
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_OK) == 2);
    assert(menu.applied == 2 && menu.previous == 0);
    {
        struct ep5_lut_menu_capture capture;
        assert(ep5_lut_menu_capture(&menu, &capture) == 1);
        assert(capture.picture_mode == 0 && capture.variant == 0 && capture.amount_q8 == 192);
    }
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_BACK) == 3);
    assert(menu.state == EP5_LUT_MENU_HIDDEN && menu.applied == 0);
    assert(ep5_lut_menu_begin_load(&menu, 3) == 1);
    assert(ep5_lut_menu_fail(&menu, 3) == 1 && menu.state == EP5_LUT_MENU_ERROR);
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_DOWN) == 1);
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_OK) == 0);
    return 0;
}
