#include "lut_wheel_view.h"

static const char names[EP5_WHEEL_SECTORS][16] = {
    "Yellow", "Orange", "Orange red", "Red", "Magenta", "Violet",
    "Blue", "Blue cyan", "Cyan", "Green cyan", "Green", "Yellow green"
};

static int focused(const struct ep5_lut_menu *menu, struct ep5_wheel_edit *out)
{
    if (!menu || menu->state != EP5_LUT_MENU_READY || menu->cursor >= EP5_LUT_MENU_SLOTS ||
        menu->applied != menu->cursor + 1u || !menu->generation)
        return 0;
    const struct ep5_lut_menu_slot *slot = &menu->slots[menu->cursor];
    if (!slot->configured || !slot->number || slot->number > 16 ||
        !slot->picture_mode || !slot->variant || slot->amount_q8 != menu->amount_q8)
        return 0;
    out->number = slot->number;
    out->look_crc = slot->look_crc;
    out->picture_mode = slot->picture_mode;
    out->variant = slot->variant;
    return 1;
}

static int current(const struct ep5_wheel_editor *e, const struct ep5_lut_menu *menu, uint32_t mount)
{
    struct ep5_wheel_edit target;
    return e && e->active && e->sector < EP5_WHEEL_SECTORS && e->field < EP5_WF_COUNT &&
           mount && mount == e->mount && focused(menu, &target) &&
           e->generation == menu->generation && ep5_wheel_same_look(&e->draft, &target);
}

static int is_ok(uint16_t ev) { return ev == 0x900c || ev == 0x900e || ev == 0x9012; }

int ep5_wheel_controls_event(struct ep5_wheel_editor *e, struct ep5_lut_menu *menu,
                             uint32_t mount, uint16_t ev, struct ep5_wheel_edit *saved)
{
    if (!e || !saved)
        return 0;
    if (!e->active) {
        struct ep5_wheel_edit target;
        if (!mount || !is_ok(ev) || !focused(menu, &target))
            return ep5_lut_menu_stock_event(menu, ev);
        int restore = ep5_wheel_same_look(saved, &target) && ep5_wheel_valid(&saved->values);
        for (unsigned axis = 0; axis < 3; ++axis)
            for (unsigned i = 0; i < EP5_WHEEL_SECTORS; ++i)
                target.values.axis[axis][i] = restore ? saved->values.axis[axis][i] : 0;
        ep5_wheel_copy(&e->draft,&target);
        e->generation = menu->generation;
        e->mount = mount;
        e->sector = 0;
        e->field = EP5_WF_SECTOR;
        e->active = 1;
        return EP5_WHEEL_OPEN;
    }
    if (!current(e, menu, mount)) {
        e->active = 0;
        return EP5_WHEEL_STALE;
    }
    if (ev == 0x9014 || ev == 0x9016) {
        e->active = 0;
        return EP5_WHEEL_CANCELLED;
    }
    if (ev == 0x9004 || ev == 0x9006) {
        e->field = (uint8_t)((e->field + (ev == 0x9006 ? 1 : EP5_WF_COUNT-1)) % EP5_WF_COUNT);
        return 1;
    }
    if (ev == 0x9008 || ev == 0x900a) {
        int step = ev == 0x900a ? 1 : -1;
        if (e->field == EP5_WF_SECTOR) {
            e->sector = (uint8_t)(((int)e->sector + step + 12) % 12);
        } else if (e->field >= EP5_WF_HUE && e->field <= EP5_WF_LIGHT) {
            int limit = e->field == EP5_WF_SAT ? 5 : 15;
            int8_t *value = &e->draft.values.axis[e->field-EP5_WF_HUE][e->sector];
            if ((step < 0 && *value > -limit) || (step > 0 && *value < limit))
                *value = (int8_t)(*value + step);
        }
        return 1;
    }
    if (!is_ok(ev))
        return 0;
    if (e->field == EP5_WF_RESET_ALL || e->field == EP5_WF_RESET_SECTOR) {
        for (unsigned i = 0; i < EP5_WHEEL_SECTORS; ++i)
            if (e->field == EP5_WF_RESET_ALL || i == e->sector)
                for (unsigned axis = 0; axis < 3; ++axis)
                    e->draft.values.axis[axis][i] = 0;
        return 1;
    }
    if (e->field == EP5_WF_SAVE) {
        ep5_wheel_copy(saved,&e->draft);
        e->active = 0;
        return EP5_WHEEL_SAVED;
    }
    e->field = (uint8_t)(e->field + 1u);
    return 1;
}

int ep5_wheel_page(const struct ep5_wheel_editor *e, const struct ep5_lut_menu *menu,
                   uint32_t mount, struct ep5_wheel_page *page)
{
    if (!page)
        return 0;
    for (unsigned i = 0; i < sizeof *page; ++i)
        ((uint8_t *)page)[i] = 0;
    if (!current(e, menu, mount))
        return 0;
    page->sector = e->sector;
    page->field = e->field;
    page->hue = e->draft.values.axis[EP5_WHEEL_HUE][e->sector];
    page->saturation = e->draft.values.axis[EP5_WHEEL_SAT][e->sector];
    page->light = e->draft.values.axis[EP5_WHEEL_LIGHT][e->sector];
    for (unsigned i = 0; i < sizeof page->sector_name - 1; ++i)
        page->sector_name[i] = names[e->sector][i];
    for (unsigned i = 0; i < EP5_LUT_MENU_LABEL_UNITS-1; ++i)
        page->look_name[i] = menu->slots[menu->cursor].label[i];
    return 1;
}
