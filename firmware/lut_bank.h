#ifndef EP5_LUT_BANK_H
#define EP5_LUT_BANK_H
#include "look_store.h"
#include "lut_menu_index.h"

/* Logical bank 1 keeps EP5LUT/INDEX.EP5. 2 and 3 map EP5LUT/... to
 * EP5LUT/B02/... and EP5LUT/B03/... . Use an independent, immutable
 * binding per bank; it must outlive all worker jobs holding its io view.
 * The caller supplies a fresh generation and invalidates old capture
 * selections before publishing the new index. */
#define EP5_LUT_BANK_COUNT 3u
#define EP5_LUT_BANK_PATH_CAP 32u
struct ep5_lut_bank {
    struct ep5_look_io parent;
    uint8_t number;
};
int ep5_lut_bank_bind(struct ep5_lut_bank *bank, struct ep5_look_io *view,
                      const struct ep5_look_io *parent, unsigned number);
int ep5_lut_bank_path(char out[EP5_LUT_BANK_PATH_CAP], unsigned number, const char *path);
unsigned ep5_lut_bank_next(unsigned number, int direction);

/* Single file-task owner. Initialize storage with {0}. select() changes the
 * menu to LOADING without doing I/O. step() does one existing worker step
 * outside the paint callback. Once READY, the selected view supplies the
 * current bank's LUT and FX files until the next select/close. */
struct ep5_lut_bank_browser {
    struct ep5_lut_bank banks[EP5_LUT_BANK_COUNT];
    struct ep5_look_io views[EP5_LUT_BANK_COUNT];
    struct ep5_lut_job job;
    struct ep5_lut_menu_slot staging[EP5_LUT_MENU_SLOTS];
    unsigned selected;
};
int ep5_lut_bank_browser_init(struct ep5_lut_bank_browser *browser, const struct ep5_look_io *parent);
int ep5_lut_bank_select(struct ep5_lut_bank_browser *browser, struct ep5_lut_menu *menu,
                        unsigned number);
int ep5_lut_bank_step(struct ep5_lut_bank_browser *browser, struct ep5_lut_menu *menu);
#endif
