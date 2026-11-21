#ifndef EP5_LUT_WHEEL_VIEW_H
#define EP5_LUT_WHEEL_VIEW_H
#include "lut_menu_adapter.h"
#include "lut_wheel.h"

enum ep5_wheel_field { EP5_WF_SECTOR, EP5_WF_HUE, EP5_WF_SAT, EP5_WF_LIGHT,
                        EP5_WF_RESET_SECTOR, EP5_WF_RESET_ALL, EP5_WF_SAVE, EP5_WF_COUNT };
enum ep5_wheel_event_result { EP5_WHEEL_OPEN = 4, EP5_WHEEL_SAVED, EP5_WHEEL_CANCELLED, EP5_WHEEL_STALE };
/* Zero-initialize once. All methods run on the same serialized UI context.
 * Supply an externally managed, nonzero mount identity, changed on card eject. */
struct ep5_wheel_editor {
    uint8_t active, sector, field;
    uint16_t generation;
    uint32_t mount;
    struct ep5_wheel_edit draft;
};
struct ep5_wheel_page {
    uint16_t look_name[EP5_LUT_MENU_LABEL_UNITS];
    char sector_name[16];
    uint8_t sector, field;
    int8_t hue, saturation, light;
};
/* Replacement dispatcher for a look-browser controller. Original list event
 * results 0..3 stay intact. OK on the focused, already confirmed row opens the
 * wheel if strength is unchanged. Zero-initialize 'saved' or decode it with
 * ep5_wheel_decode. Only a successful user save writes the caller's value. */
int ep5_wheel_controls_event(struct ep5_wheel_editor *editor, struct ep5_lut_menu *menu,
                             uint32_t mount, uint16_t stock_event, struct ep5_wheel_edit *saved);
int ep5_wheel_page(const struct ep5_wheel_editor *editor, const struct ep5_lut_menu *menu,
                   uint32_t mount, struct ep5_wheel_page *page);
#endif
