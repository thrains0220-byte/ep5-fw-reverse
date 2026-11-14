#ifndef EP5_LUT_MENU_H
#define EP5_LUT_MENU_H

#include <stdint.h>

#define EP5_LUT_MENU_SLOTS 3u
#define EP5_LUT_MENU_LABEL_UNITS 16u
#define EP5_LUT_MENU_STORAGE_BYTES 128u

enum ep5_lut_menu_state {
    EP5_LUT_MENU_HIDDEN = 0,
    EP5_LUT_MENU_LOADING = 1,
    EP5_LUT_MENU_READY = 2,
    EP5_LUT_MENU_ERROR = 3,
};

enum ep5_lut_menu_event {
    EP5_LUT_MENU_UP = 1,
    EP5_LUT_MENU_DOWN = 2,
    EP5_LUT_MENU_LEFT = 3,
    EP5_LUT_MENU_RIGHT = 4,
    EP5_LUT_MENU_OK = 5,
    EP5_LUT_MENU_BACK = 6,
};

struct ep5_lut_menu_slot {
    uint16_t picture_mode;
    uint8_t variant;
    uint8_t configured;
    uint16_t amount_q8;
    uint16_t number;
    uint16_t label[EP5_LUT_MENU_LABEL_UNITS];
};

struct ep5_lut_menu {
    uint8_t state;
    uint8_t cursor;
    uint8_t applied;
    uint8_t previous;
    uint16_t amount_q8;
    uint16_t generation;
    struct ep5_lut_menu_slot slots[EP5_LUT_MENU_SLOTS];
};

struct ep5_lut_menu_capture {
    uint16_t picture_mode;
    uint8_t variant;
    uint16_t amount_q8;
    uint16_t number;
};

typedef char ep5_lut_menu_storage_size_check[
    (sizeof(struct ep5_lut_menu) == EP5_LUT_MENU_STORAGE_BYTES) ? 1 : -1];

void ep5_lut_menu_init(struct ep5_lut_menu *menu);
int ep5_lut_menu_event(struct ep5_lut_menu *menu, enum ep5_lut_menu_event event);
int ep5_lut_menu_begin_load(struct ep5_lut_menu *menu, uint16_t generation);
int ep5_lut_menu_publish(struct ep5_lut_menu *menu, uint16_t generation,
                         const struct ep5_lut_menu_slot *slots);
int ep5_lut_menu_fail(struct ep5_lut_menu *menu, uint16_t generation);
int ep5_lut_menu_capture(const volatile struct ep5_lut_menu *menu,
                         struct ep5_lut_menu_capture *capture);

#endif
