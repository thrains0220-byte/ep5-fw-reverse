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

int ep5_lut_menu_page(const struct ep5_lut_menu *menu, struct ep5_look_page *page)
{
    if (!page)
        return 0;
    /* Also discard old text when the same destination is reused after eject. */
    for (unsigned i = 0; i < sizeof *page; ++i)
        ((uint8_t *)page)[i] = 0;
    if (!menu || menu->state == EP5_LUT_MENU_HIDDEN)
        return 0;
    page->state = menu->state;
    if (menu->state != EP5_LUT_MENU_READY)
        return 1;

    unsigned before_cursor = 0;
    for (unsigned i = 0; i < EP5_LUT_MENU_SLOTS && i < menu->cursor; ++i)
        before_cursor += menu->slots[i].configured != 0;
    page->first = (uint8_t)(before_cursor / EP5_LOOK_PAGE_ROWS * EP5_LOOK_PAGE_ROWS);
    for (unsigned i = 0; i < EP5_LUT_MENU_SLOTS; ++i) {
        const struct ep5_lut_menu_slot *slot = &menu->slots[i];
        if (!slot->configured)
            continue;
        unsigned ordinal = page->total++;
        if (ordinal < page->first || page->count == EP5_LOOK_PAGE_ROWS)
            continue;
        struct ep5_look_page_row *row = &page->rows[page->count++];
        row->focused = menu->cursor == i;
        row->confirmed = menu->applied == i + 1;
        unsigned amount = row->focused ? menu->amount_q8 : slot->amount_q8;
        row->percent = (uint8_t)((100u * amount + 128u) / 256u);
        for (unsigned unit = 0; unit + 1 < EP5_LUT_MENU_LABEL_UNITS; ++unit)
            row->name[unit] = slot->label[unit];
    }
    return 1;
}
