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

static void copy_label(uint16_t *destination, const volatile uint16_t *source)
{
    for (unsigned index = 0; index < EP5_LUT_MENU_LABEL_UNITS; ++index)
        destination[index] = source[index];
}

unsigned ep5_lut_menu_lines(const volatile struct ep5_lut_menu *menu,
                            struct ep5_lut_menu_line *lines, unsigned capacity)
{
    unsigned required = 1u + EP5_LUT_MENU_SLOTS + 1u;
    if (!menu)
        return 0;
    if (!lines || capacity < required)
        return required;
    for (unsigned index = 0; index < required; ++index) {
        lines[index].kind = index == 0 ? EP5_LUT_MENU_LINE_TITLE :
            (index <= EP5_LUT_MENU_SLOTS ? EP5_LUT_MENU_LINE_SLOT : EP5_LUT_MENU_LINE_STATUS);
        lines[index].selected = 0;
        lines[index].configured = 0;
        lines[index].reserved = 0;
        lines[index].amount_q8 = 0;
        lines[index].number = 0;
        for (unsigned unit = 0; unit < EP5_LUT_MENU_LABEL_UNITS; ++unit)
            lines[index].text[unit] = 0;
    }
    lines[0].text[0] = 'L'; lines[0].text[1] = 'U'; lines[0].text[2] = 'T';
    lines[0].text[3] = ' '; lines[0].text[4] = 'L'; lines[0].text[5] = 'O';
    lines[0].text[6] = 'O'; lines[0].text[7] = 'K';
    for (unsigned index = 0; index < EP5_LUT_MENU_SLOTS; ++index) {
        const volatile struct ep5_lut_menu_slot *slot = &menu->slots[index];
        struct ep5_lut_menu_line *line = &lines[index + 1];
        line->selected = menu->state == EP5_LUT_MENU_READY && menu->cursor == index;
        line->configured = slot->configured;
        line->amount_q8 = slot->amount_q8;
        line->number = slot->number;
        copy_label(line->text, slot->label);
    }
    lines[required - 1].text[0] = menu->state == EP5_LUT_MENU_LOADING ? 'L' :
        (menu->state == EP5_LUT_MENU_ERROR ? 'E' : 'O');
    lines[required - 1].text[1] = menu->state == EP5_LUT_MENU_LOADING ? 'O' :
        (menu->state == EP5_LUT_MENU_ERROR ? 'R' : 'K');
    lines[required - 1].text[2] = menu->state == EP5_LUT_MENU_LOADING ? 'A' :
        (menu->state == EP5_LUT_MENU_ERROR ? 'R' : ' ');
    lines[required - 1].text[3] = menu->state == EP5_LUT_MENU_LOADING ? 'D' :
        (menu->state == EP5_LUT_MENU_ERROR ? '!' : ' ');
    return required;
}
