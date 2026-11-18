/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Synthetic adapter for the offline ART/JPEG model. These addresses and
 * the single-thread lock are supplied by the probe, not by the camera. */
#include "lut_preload.h"

struct model_state {
    struct ep5_lut_preload loader;
    uint32_t medium, last_shot, shot;
    int locked;
};

#define MODEL ((struct model_state *)(uintptr_t)0x11006000u)
#define TABLES ((uint16_t *)(uintptr_t)0x12010000u)

extern volatile struct ep5_lut_menu ep5_lut_menu_storage;
extern void *look_open(void *context, const char *path);
extern int32_t look_read(void *context, void *file, uint8_t *destination, uint32_t count);
extern int look_close(void *context, void *file);

static void lock(void *context)
{
    struct model_state *state = context;
    state->locked = 1;
}

static void unlock(void *context)
{
    struct model_state *state = context;
    state->locked = 0;
}

static void *open_mounted(void *context, uint32_t medium, const char *path)
{
    struct model_state *state = context;
    return !state->locked && state->medium == medium ? look_open(NULL, path) : NULL;
}

static int32_t read_file(void *context, void *file, uint8_t *destination, uint32_t count)
{
    struct model_state *state = context;
    return state->locked ? -1 : look_read(NULL, file, destination, count);
}

static int close_file(void *context, void *file)
{
    struct model_state *state = context;
    return state->locked ? -1 : look_close(NULL, file);
}

int ep5_model_acquire(const struct ep5_lut_menu_capture *choice,
                      struct ep5_look_selection *selection)
{
    const uint32_t shot = ++MODEL->last_shot;
    if (!ep5_lut_preload_acquire(&MODEL->loader, MODEL->medium, shot, choice, selection))
        return 0;
    MODEL->shot = shot;
    return 1;
}

void ep5_model_release(void)
{
    if (ep5_lut_preload_release(&MODEL->loader, MODEL->shot))
        MODEL->shot = 0;
}

int ep5_model_worker(unsigned operation)
{
    if (operation == 0) {
        struct ep5_lut_menu_capture choice;
        const struct ep5_lut_preload_io io = {MODEL, open_mounted, read_file, close_file};
        const struct ep5_lut_preload_sync sync = {MODEL, lock, unlock};
        if (!ep5_lut_preload_init(&MODEL->loader, &io, &sync, TABLES, TABLES + EP5_LUT_VALUES,
                                  2u * EP5_LUT_VALUES) ||
            !ep5_lut_menu_capture(&ep5_lut_menu_storage, &choice))
            return 0;
        MODEL->medium = 1;
        ep5_lut_preload_media(&MODEL->loader, MODEL->medium);
        return ep5_lut_preload_select(&MODEL->loader, MODEL->medium, &choice);
    }
    if (operation == 1)
        return ep5_lut_preload_step(&MODEL->loader);
    if (operation == 2) {
        MODEL->medium = 0;
        ep5_lut_preload_media(&MODEL->loader, 0);
        return 0;
    }
    return MODEL->shot != 0 || MODEL->loader.pinned != NULL;
}
