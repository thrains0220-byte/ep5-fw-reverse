#include "lut_menu.h"

static void clear_label(uint16_t *label)
{
    for (unsigned index = 0; index < EP5_LUT_MENU_LABEL_UNITS; ++index)
        label[index] = 0;
}

void ep5_lut_menu_init(struct ep5_lut_menu *menu)
{
    if (!menu)
        return;
    menu->state = EP5_LUT_MENU_HIDDEN;
    menu->cursor = 0;
    menu->applied = 0;
    menu->previous = 0;
    menu->amount_q8 = 256;
    menu->generation = 0;
    for (unsigned index = 0; index < EP5_LUT_MENU_SLOTS; ++index) {
        menu->slots[index].picture_mode = 0;
        menu->slots[index].variant = 0;
        menu->slots[index].configured = 0;
        menu->slots[index].amount_q8 = 0;
        menu->slots[index].number = 0;
        clear_label(menu->slots[index].label);
    }
}

int ep5_lut_menu_begin_load(struct ep5_lut_menu *menu, uint16_t generation)
{
    if (!menu || !generation)
        return 0;
    menu->state = EP5_LUT_MENU_LOADING;
    menu->generation = generation;
    menu->applied = 0;
    return 1;
}

int ep5_lut_menu_publish(struct ep5_lut_menu *menu, uint16_t generation,
                         const struct ep5_lut_menu_slot *slots)
{
    if (!menu || !slots || !generation || menu->state != EP5_LUT_MENU_LOADING ||
        menu->generation != generation)
        return 0;
    for (unsigned index = 0; index < EP5_LUT_MENU_SLOTS; ++index)
        menu->slots[index] = slots[index];
    menu->state = EP5_LUT_MENU_READY;
    if (menu->cursor >= EP5_LUT_MENU_SLOTS)
        menu->cursor = 0;
    menu->amount_q8 = menu->slots[menu->cursor].amount_q8;
    return 1;
}

int ep5_lut_menu_fail(struct ep5_lut_menu *menu, uint16_t generation)
{
    if (!menu || !generation || menu->generation != generation ||
        menu->state != EP5_LUT_MENU_LOADING)
        return 0;
    menu->state = EP5_LUT_MENU_ERROR;
    menu->applied = 0;
    return 1;
}

static void move_cursor(struct ep5_lut_menu *menu, int step)
{
    unsigned cursor = menu->cursor;
    if (step > 0)
        cursor = (cursor + 1u) % EP5_LUT_MENU_SLOTS;
    else
        cursor = (cursor + EP5_LUT_MENU_SLOTS - 1u) % EP5_LUT_MENU_SLOTS;
    menu->cursor = (uint8_t)cursor;
    menu->amount_q8 = menu->slots[cursor].amount_q8;
}

int ep5_lut_menu_event(struct ep5_lut_menu *menu, enum ep5_lut_menu_event event)
{
    if (!menu)
        return 0;
    if (event == EP5_LUT_MENU_BACK) {
        menu->state = EP5_LUT_MENU_HIDDEN;
        menu->applied = 0;
        return 3;
    }
    if (menu->state == EP5_LUT_MENU_LOADING)
        return 1;
    if (menu->state == EP5_LUT_MENU_ERROR && event != EP5_LUT_MENU_OK)
        return 1;
    if (menu->state != EP5_LUT_MENU_READY)
        return 0;
    switch (event) {
    case EP5_LUT_MENU_UP:
    case EP5_LUT_MENU_LEFT:
        move_cursor(menu, -1);
        return 1;
    case EP5_LUT_MENU_DOWN:
    case EP5_LUT_MENU_RIGHT:
        move_cursor(menu, 1);
        return 1;
    case EP5_LUT_MENU_OK:
        if (!menu->slots[menu->cursor].configured)
            return 1;
        menu->previous = menu->applied;
        menu->applied = (uint8_t)(menu->cursor + 1u);
        menu->generation = (uint16_t)(menu->generation + 1u);
        if (!menu->generation)
            menu->generation = 1;
        return 2;
    default:
        return 0;
    }
}

int ep5_lut_menu_capture(const volatile struct ep5_lut_menu *menu,
                         struct ep5_lut_menu_capture *capture)
{
    uint16_t before, after;
    uint8_t applied;
    const volatile struct ep5_lut_menu_slot *slot;
    if (!menu || !capture)
        return 0;
    before = menu->generation;
    if (menu->state != EP5_LUT_MENU_READY ||
        (applied = menu->applied) < 1 || applied > EP5_LUT_MENU_SLOTS)
        return 0;
    slot = &menu->slots[applied - 1];
    if (!slot->configured)
        return 0;
    capture->picture_mode = slot->picture_mode;
    capture->variant = slot->variant;
    capture->amount_q8 = slot->amount_q8;
    capture->number = slot->number;
    after = menu->generation;
    return before == after && menu->state == EP5_LUT_MENU_READY && menu->applied == applied;
}
