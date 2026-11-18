/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Synthetic adapter for the offline ART/JPEG model. These addresses and
 * the single-thread lock are supplied by the probe, not by the camera. */
#include "lut_preload.h"
#include "lut_menu_adapter.h"
#include "lut_menu_index.h"

struct model_state {
    struct ep5_lut_preload loader;
    struct ep5_lut_job index_job;
    struct ep5_lut_menu_slot index_slots[EP5_LUT_MENU_SLOTS];
    uint32_t medium, index_medium, last_shot, shot;
    int locked, initialized;
};

#define MODEL ((struct model_state *)(uintptr_t)0x11006000u)
#define TABLES ((uint16_t *)(uintptr_t)0x12010000u)

extern struct ep5_lut_menu ep5_lut_menu;
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

static void *open_index(void *context, const char *path)
{
    struct model_state *state = context;
    return open_mounted(state, state->index_medium, path);
}

static int request_index(uint16_t generation)
{
    const struct ep5_look_io io = {MODEL, open_index, read_file, close_file};
    MODEL->index_medium = MODEL->medium;
    return ep5_lut_job_request_index(&MODEL->index_job, &io, MODEL->index_slots, generation) &&
        ep5_lut_menu_begin_load(&ep5_lut_menu, generation);
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
        if (!ep5_lut_menu_capture(&ep5_lut_menu, &choice))
            return 0;
        if (!MODEL->initialized) {
            const struct ep5_lut_preload_io io = {MODEL, open_mounted, read_file, close_file};
            const struct ep5_lut_preload_sync sync = {MODEL, lock, unlock};
            if (!ep5_lut_preload_init(&MODEL->loader, &io, &sync, TABLES, TABLES + EP5_LUT_VALUES,
                                      2u * EP5_LUT_VALUES))
                return 0;
            MODEL->initialized = 1;
            MODEL->medium = 1;
            ep5_lut_preload_media(&MODEL->loader, MODEL->medium);
        }
        return ep5_lut_preload_select(&MODEL->loader, MODEL->medium, &choice);
    }
    if (operation == 1)
        return ep5_lut_preload_step(&MODEL->loader);
    if (operation == 2) {
        MODEL->medium = 0;
        ep5_lut_preload_media(&MODEL->loader, 0);
        return 0;
    }
    if (operation == 3)
        return MODEL->shot != 0 || MODEL->loader.pinned != NULL;
    if (operation == 4) {
        ep5_lut_menu_init(&ep5_lut_menu);
        ep5_lut_job_init(&MODEL->index_job);
        MODEL->medium = 1;
        return request_index(1);
    }
    if (operation == 5) {
        uint16_t generation = MODEL->medium == MODEL->index_medium ? ep5_lut_menu.generation : 0;
        int status = ep5_lut_job_step(&MODEL->index_job, generation);
        if (generation && status != EP5_LUT_JOB_BUSY && status != EP5_LUT_JOB_CANCELLED) {
            lock(MODEL);
            int published = ep5_lut_menu_finish_index(&MODEL->index_job, &ep5_lut_menu);
            unlock(MODEL);
            if (status == EP5_LUT_JOB_INDEX_READY && !published)
                return EP5_LUT_JOB_ERROR;
        }
        return status;
    }
    if (operation == 6) {
        if (ep5_lut_menu.state != EP5_LUT_MENU_READY || ep5_lut_menu.cursor > 5)
            return 0;
        while (ep5_lut_menu.cursor < 5)
            if (ep5_lut_menu_stock_event(&ep5_lut_menu, 0x9006) != 1)
                return 0;
        return ep5_lut_menu_stock_event(&ep5_lut_menu, 0x900c) == 2;
    }
    if (operation == 7 && !MODEL->medium && MODEL->initialized) {
        MODEL->medium = 2;
        ep5_lut_preload_media(&MODEL->loader, MODEL->medium);
        return request_index(2);
    }
    return 0;
}
