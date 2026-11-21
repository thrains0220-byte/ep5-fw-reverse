#ifndef EP5_LUT_CAMERA_MENU_H
#define EP5_LUT_CAMERA_MENU_H
#include "lut_bank.h"
#include "lut_wheel_draw.h"

enum ep5_camera_page { EP5_CAMERA_CLOSED, EP5_CAMERA_GROUPS, EP5_CAMERA_LOOKS };
enum ep5_camera_action { EP5_CAMERA_SHOW_GROUPS = 8, EP5_CAMERA_LOAD_GROUP = 9,
                         EP5_CAMERA_SAVE_REQUEST = 10, EP5_CAMERA_SAVE_COMPLETE = 11,
                         EP5_CAMERA_KEY_CONSUMED = 12 };
/* Optional file-worker backend. Each call operates on the indicated mount,
 * never on a drive name rebound to a different card. load returns 1 for an
 * exact 56-byte record, 0 for missing, negative for error (including oversize).
 * replace returns 1 only after atomic publication. Every other result leaves
 * the previous committed record intact. Paths are relative to this mount. */
struct ep5_camera_wheel_store {
    void *ctx;
    int (*load)(void *ctx, uint32_t mount, const char *path, uint8_t record[EP5_WHEEL_FILE_BYTES]);
    int (*replace)(void *ctx, uint32_t mount, const char *path, const uint8_t record[EP5_WHEEL_FILE_BYTES]);
};
struct ep5_camera_wheel_job {
    struct ep5_camera_wheel_store store;
    uint32_t mount, ticket;
    uint8_t bank, slot, write;
    char path[24];
    uint8_t record[EP5_WHEEL_FILE_BYTES];
};
enum ep5_camera_wheel_write { EP5_CAMERA_WRITE_IDLE, EP5_CAMERA_WRITE_QUEUED, EP5_CAMERA_WRITE_FAILED };
enum ep5_camera_dial { EP5_CAMERA_MAIN_DIAL = 1, EP5_CAMERA_SUB_DIAL };
enum ep5_camera_release { EP5_CAMERA_FOCUS_LOST = 1, EP5_CAMERA_HALF_SHUTTER,
                          EP5_CAMERA_PLAYBACK, EP5_CAMERA_POWER_OFF };
struct ep5_camera_choice {
    uint32_t mount, revision;
    uint8_t bank, has_wheel;
    struct ep5_lut_menu_capture look;
    struct ep5_wheel_values wheel;
};
/* One owner serializes events and job steps. Do not reinitialize this object
 * until the previous file job has completed or cancelled and closed. */
struct ep5_camera_menu {
    struct ep5_lut_bank_browser browser;
    struct ep5_lut_menu looks;
    struct ep5_wheel_editor wheel;
    struct ep5_wheel_edit saved[EP5_LUT_BANK_COUNT][EP5_LUT_MENU_SLOTS];
    struct ep5_camera_wheel_store store;
    struct ep5_camera_choice confirmed;
    uint32_t mount, revision, wheel_ticket, foreground, finishing_write;
    uint16_t unreadable_edits;
    uint8_t page, group_focus, pending, restore_next, wheel_write, wheel_inflight;
};
int ep5_camera_menu_init(struct ep5_camera_menu *ui, const struct ep5_look_io *io, uint32_t mount);
/* Attach after init, before first group request. The no-backend variant
 * retains the original per-mount, in-memory behavior. The owner schedules
 * step on EP5_CAMERA_SAVE_REQUEST and on group open; no event does file IO. */
int ep5_camera_menu_attach_store(struct ep5_camera_menu *ui, const struct ep5_camera_wheel_store *store);
/* Nonblocking cross-task interface. The menu owner calls take and finish.
 * The file worker owns the snapshot between those calls and executes IO
 * without touching the menu or holding its lock. Serialize backend calls.
 * Keep the backend and its mount lease valid until outstanding calls return.
 * take returns 1 when it issued a job. Never execute a snapshot twice. */
int ep5_camera_wheel_take(struct ep5_camera_menu *ui, uint32_t mount, struct ep5_camera_wheel_job *job);
int ep5_camera_wheel_execute(struct ep5_camera_wheel_job *job);
int ep5_camera_wheel_finish(struct ep5_camera_menu *ui, uint32_t mount,
                            const struct ep5_camera_wheel_job *job, int result);
int ep5_camera_menu_open(struct ep5_camera_menu *ui, uint32_t mount);
/* Tag events at acquisition. Zero means stock owns this event. Recognized
 * events tagged with a closed/older foreground are consumed without action,
 * including after a card change. Unknown controls pass through to stock. */
uint32_t ep5_camera_menu_foreground(const struct ep5_camera_menu *ui, uint32_t mount);
int ep5_camera_menu_dial(struct ep5_camera_menu *ui, uint32_t mount, uint32_t foreground,
                         enum ep5_camera_dial dial, int16_t detents);
int ep5_camera_menu_key(struct ep5_camera_menu *ui, uint32_t mount, uint32_t foreground, uint16_t key);
/* Notify before forwarding the very same half-press/playback/power/focus event
 * to stock. Always forward it, even if the page was already closed. */
void ep5_camera_menu_release(struct ep5_camera_menu *ui, uint32_t mount, uint32_t foreground,
                             enum ep5_camera_release reason);
int ep5_camera_menu_event(struct ep5_camera_menu *ui, uint32_t mount, uint16_t key);
/* File owner calls step while BUSY. Pass zero on eject, continue until closed. */
int ep5_camera_menu_step(struct ep5_camera_menu *ui, uint32_t mount);
int ep5_camera_menu_draw(const struct ep5_camera_menu *ui, uint32_t mount,
                         const struct ep5_wheel_surface *surface);
/* The caller uses browser.views[bank-1] and the same mount for loading the
 * chosen table/FX. Revalidate the full choice before publishing a result. */
int ep5_camera_menu_capture(const struct ep5_camera_menu *ui, uint32_t mount, struct ep5_camera_choice *out);
int ep5_camera_menu_choice_current(const struct ep5_camera_menu *ui, uint32_t mount,
                                   const struct ep5_camera_choice *choice);
#endif
