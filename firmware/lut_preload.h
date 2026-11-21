#ifndef EP5_LUT_PRELOAD_H
#define EP5_LUT_PRELOAD_H

#include "lut_job.h"
#include "lut_menu.h"

struct ep5_lut_preload_sync {
    void *context;
    void (*lock)(void *context);
    void (*unlock)(void *context);
};

/* Open must validate the requested mount and bind the returned handle to it
 * as one operation. Read and close act on that handle even after unmount. */
struct ep5_lut_preload_io {
    void *context;
    void *(*open)(void *context, uint32_t medium, const char *path);
    int32_t (*read)(void *context, void *file, uint8_t *destination, uint32_t count);
    int (*close)(void *context, void *file);
};

struct ep5_lut_preload {
    struct ep5_lut_preload_io io;
    struct ep5_lut_preload_sync sync;
    struct ep5_look_cache cache;
    struct ep5_lut_job job;
    struct ep5_lut_menu_capture desired;
    struct ep5_look_selection published;
    const uint16_t *pinned;
    uint32_t medium, job_medium, shot;
    uint8_t status, running, discard, stepping;
};

enum ep5_lut_preload_step_status {
    EP5_LUT_PRELOAD_WAIT_SHOT = EP5_LUT_JOB_CANCELLED + 1
};

/* Initialize once, before sharing the loader. The lock must serialize tasks
 * and provide visibility for shared metadata and completed table writes. */
int ep5_lut_preload_init(struct ep5_lut_preload *loader, const struct ep5_lut_preload_io *io,
                         const struct ep5_lut_preload_sync *sync,
                         void *first, void *second, size_t table_bytes);
/* Zero means unmounted. Assign a fresh nonzero ID to each mount or refresh. */
void ep5_lut_preload_media(struct ep5_lut_preload *loader, uint32_t medium);
int ep5_lut_preload_select(struct ep5_lut_preload *loader, uint32_t medium,
                           const struct ep5_lut_menu_capture *choice);
/* Called by the file worker. BUSY means more work. WAIT_SHOT means suspend
 * until the shot releases staging or the pending request is invalidated. */
int ep5_lut_preload_step(struct ep5_lut_preload *loader);
enum ep5_lut_job_status ep5_lut_preload_status(struct ep5_lut_preload *loader, uint32_t medium,
                                               const struct ep5_lut_menu_capture *choice);
/* Acquires exactly the confirmed choice. Supply a fresh nonzero shot ID and
 * release it on every exit after all readers are done using the table. */
int ep5_lut_preload_acquire(struct ep5_lut_preload *loader, uint32_t medium,
                            uint32_t shot, const struct ep5_lut_menu_capture *choice,
                            struct ep5_look_selection *selection);
int ep5_lut_preload_release(struct ep5_lut_preload *loader, uint32_t shot);

#endif
