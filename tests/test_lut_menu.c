#include <assert.h>
#include <string.h>
#include "lut_menu.h"
#include "lut_menu_index.h"

static void slot(struct ep5_lut_menu_slot *value, unsigned number, unsigned amount)
{
    memset(value, 0, sizeof *value);
    value->configured = 1;
    value->number = (uint16_t)number;
    value->look_crc = 0x12340000u + number;
    value->amount_q8 = (uint16_t)amount;
    value->label[0] = (uint16_t)('A' + number);
}

int main(void)
{
    struct ep5_lut_menu menu;
    struct ep5_lut_menu_slot slots[EP5_LUT_MENU_SLOTS];
    memset(slots, 0, sizeof slots);
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
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_RIGHT) == 1);
    {
        struct ep5_lut_menu_line lines[EP5_LUT_MENU_LINE_COUNT];
        assert(ep5_lut_menu_lines(&menu, lines, EP5_LUT_MENU_LINE_COUNT) == EP5_LUT_MENU_LINE_COUNT);
        assert(lines[2].selected && lines[2].amount_q8 == 208);
    }
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_LEFT) == 1);
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_OK) == 2);
    assert(menu.applied == 2 && menu.previous == 0);
    {
        struct ep5_lut_menu_capture capture;
        assert(ep5_lut_menu_capture(&menu, &capture) == 1);
        assert(capture.picture_mode == 0 && capture.variant == 0 && capture.amount_q8 == 192);
        {
            uint16_t amount = 999;
            assert(ep5_lut_menu_amount(&capture, 2, 0x12340002u, &amount) && amount == 192);
            assert(!ep5_lut_menu_amount(&capture, 1, 0x12340002u, &amount));
            assert(!ep5_lut_menu_amount(&capture, 2, 0x12340003u, &amount));
            capture.amount_q8 = 0;
            assert(!ep5_lut_menu_amount(&capture, 2, 0x12340002u, &amount));
            capture.amount_q8 = 257;
            assert(!ep5_lut_menu_amount(&capture, 2, 0x12340002u, &amount));
        }
    {
        struct ep5_lut_menu_line lines[EP5_LUT_MENU_LINE_COUNT];
        assert(ep5_lut_menu_lines(&menu, lines, EP5_LUT_MENU_LINE_COUNT) == EP5_LUT_MENU_LINE_COUNT);
        assert(lines[0].kind == EP5_LUT_MENU_LINE_TITLE);
        assert(lines[2].selected && lines[2].amount_q8 == 192);
        assert(ep5_lut_menu_lines(&menu, 0, 0) == EP5_LUT_MENU_LINE_COUNT);
    }
    }
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_BACK) == 3);
    assert(menu.state == EP5_LUT_MENU_HIDDEN && menu.applied == 2);
    {
        struct ep5_lut_menu_capture capture;
        assert(ep5_lut_menu_capture(&menu, &capture));
        assert(capture.number == 2 && capture.amount_q8 == 192 && capture.look_crc == 0x12340002u);
    }
    /* Reopening and re-reading an unchanged card retains the confirmed look
     * and user-adjusted amount, but cannot capture while loading. */
    assert(ep5_lut_menu_begin_load(&menu, 10));
    {
        struct ep5_lut_menu_capture capture;
        assert(!ep5_lut_menu_capture(&menu, &capture));
        slots[1].amount_q8 = 64;
        assert(ep5_lut_menu_publish(&menu, 10, slots));
        assert(ep5_lut_menu_capture(&menu, &capture));
        assert(capture.number == 2 && capture.amount_q8 == 192);
    }
    /* A replaced card or modified LUT must be confirmed again. */
    assert(ep5_lut_menu_begin_load(&menu, 11));
    slots[1].look_crc ^= 1;
    assert(ep5_lut_menu_publish(&menu, 11, slots));
    {
        struct ep5_lut_menu_capture capture;
        assert(!ep5_lut_menu_capture(&menu, &capture));
    }
    slot(&slots[0], 1, 128);
    assert(ep5_lut_menu_begin_load(&menu, menu.generation - 1u) == 1);
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_BACK) == 3);
    assert(ep5_lut_menu_publish(&menu, menu.generation - 1u, slots) == 0);
    assert(ep5_lut_menu_begin_load(&menu, 3) == 1);
    assert(ep5_lut_menu_fail(&menu, 3) == 1 && menu.state == EP5_LUT_MENU_ERROR);
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_DOWN) == 1);
    assert(ep5_lut_menu_event(&menu, EP5_LUT_MENU_OK) == 0);
    return 0;
}
