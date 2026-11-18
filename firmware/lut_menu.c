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
        menu->slots[index].look_crc = 0;
        clear_label(menu->slots[index].label);
    }
}

int ep5_lut_menu_begin_load(struct ep5_lut_menu *menu, uint16_t generation)
{
    if (!menu || !generation)
        return 0;
    menu->state = EP5_LUT_MENU_LOADING;
    menu->generation = generation;
    /* Capture is disabled while loading. Keep the old identity only long
     * enough for publish to check it against the newly read card index. */
    return 1;
}

int ep5_lut_menu_publish(struct ep5_lut_menu *menu, uint16_t generation,
                         const struct ep5_lut_menu_slot *slots)
{
    uint8_t retain = 0;
    uint16_t retained_amount = 0;
    if (!menu || !slots || !generation || menu->state != EP5_LUT_MENU_LOADING ||
        menu->generation != generation)
        return 0;
    if (menu->applied >= 1 && menu->applied <= EP5_LUT_MENU_SLOTS) {
        unsigned index = menu->applied - 1u;
        const struct ep5_lut_menu_slot *old = &menu->slots[index];
        const struct ep5_lut_menu_slot *next = &slots[index];
        if (old->configured && next->configured && old->picture_mode == next->picture_mode &&
            old->variant == next->variant && old->number == next->number &&
            old->look_crc == next->look_crc && old->amount_q8 <= 256) {
            retain = menu->applied;
            retained_amount = old->amount_q8;
        }
    }
    /* The freestanding MN103 build has no libc memcpy. */
    for (unsigned index = 0; index < EP5_LUT_MENU_SLOTS; ++index) {
        uint8_t *destination = (uint8_t *)&menu->slots[index];
        const uint8_t *source = (const uint8_t *)&slots[index];
        for (unsigned byte = 0; byte < sizeof slots[index]; ++byte)
            destination[byte] = source[byte];
    }
    menu->applied = retain;
    if (retain)
        menu->slots[retain - 1u].amount_q8 = retained_amount;
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

static void adjust_amount(struct ep5_lut_menu *menu, int step)
{
    int amount = (int)menu->amount_q8 + step * 16;
    if (amount < 0)
        amount = 0;
    if (amount > 256)
        amount = 256;
    menu->amount_q8 = (uint16_t)amount;
}

static void invalidate_generation(struct ep5_lut_menu *menu)
{
    menu->generation = (uint16_t)(menu->generation + 1u);
    if (!menu->generation)
        menu->generation = 1;
}

int ep5_lut_menu_event(struct ep5_lut_menu *menu, enum ep5_lut_menu_event event)
{
    if (!menu)
        return 0;
    if (event == EP5_LUT_MENU_BACK) {
        invalidate_generation(menu);
        /* Closing a ready menu keeps the confirmed choice for capture.
         * An incomplete or failed index has no usable selection. */
        if (menu->state != EP5_LUT_MENU_READY)
            menu->applied = 0;
        menu->state = EP5_LUT_MENU_HIDDEN;
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
        move_cursor(menu, -1);
        return 1;
    case EP5_LUT_MENU_DOWN:
        move_cursor(menu, 1);
        return 1;
    case EP5_LUT_MENU_LEFT:
        adjust_amount(menu, -1);
        return 1;
    case EP5_LUT_MENU_RIGHT:
        adjust_amount(menu, 1);
        return 1;
    case EP5_LUT_MENU_OK:
        if (!menu->slots[menu->cursor].configured)
            return 1;
        menu->slots[menu->cursor].amount_q8 = menu->amount_q8;
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
    if ((menu->state != EP5_LUT_MENU_READY && menu->state != EP5_LUT_MENU_HIDDEN) ||
        (applied = menu->applied) < 1 || applied > EP5_LUT_MENU_SLOTS)
        return 0;
    slot = &menu->slots[applied - 1];
    if (!slot->configured)
        return 0;
    capture->picture_mode = slot->picture_mode;
    capture->variant = slot->variant;
    capture->amount_q8 = slot->amount_q8;
    capture->number = slot->number;
    capture->look_crc = slot->look_crc;
    after = menu->generation;
    return before == after &&
        (menu->state == EP5_LUT_MENU_READY || menu->state == EP5_LUT_MENU_HIDDEN) &&
        menu->applied == applied;
}

int ep5_lut_menu_amount(const struct ep5_lut_menu_capture *capture,
                        uint16_t loaded_number, uint32_t loaded_crc,
                        uint16_t *amount_q8)
{
    if (!capture || !amount_q8 || !loaded_number || loaded_number > 16 ||
        capture->number != loaded_number || capture->look_crc != loaded_crc ||
        !capture->amount_q8 ||
        capture->amount_q8 > 256)
        return 0;
    *amount_q8 = capture->amount_q8;
    return 1;
}

static void copy_label(uint16_t *destination, const volatile uint16_t *source)
{
    for (unsigned index = 0; index < EP5_LUT_MENU_LABEL_UNITS; ++index)
        destination[index] = source[index];
}

unsigned ep5_lut_menu_lines(const volatile struct ep5_lut_menu *menu,
                            struct ep5_lut_menu_line *lines, unsigned capacity)
{
    unsigned required = EP5_LUT_MENU_LINE_COUNT;
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
        line->amount_q8 = line->selected ? menu->amount_q8 : slot->amount_q8;
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
