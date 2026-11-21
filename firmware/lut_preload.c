/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "lut_preload.h"

static int same_table(const struct ep5_lut_menu_capture *first,
                       const struct ep5_lut_menu_capture *second)
{
    return first->picture_mode == second->picture_mode && first->variant == second->variant &&
        first->number == second->number && first->look_crc == second->look_crc;
}

static void invalidate(struct ep5_lut_preload *loader, uint8_t status)
{
    loader->published = (struct ep5_look_selection){0};
    loader->status = status;
    loader->discard = loader->running;
}

static void *open_on_medium(void *context, const char *path)
{
    struct ep5_lut_preload *loader = context;
    return loader->io.open(loader->io.context, loader->job_medium, path);
}

static int32_t read_on_medium(void *context, void *file, uint8_t *destination, uint32_t count)
{
    struct ep5_lut_preload *loader = context;
    return loader->io.read(loader->io.context, file, destination, count);
}

static int close_on_medium(void *context, void *file)
{
    struct ep5_lut_preload *loader = context;
    return loader->io.close(loader->io.context, file);
}

int ep5_lut_preload_init(struct ep5_lut_preload *loader, const struct ep5_lut_preload_io *io,
                         const struct ep5_lut_preload_sync *sync,
                         void *first, void *second, size_t table_bytes)
{
    if (!loader || !io || !io->open || !io->read || !io->close ||
        !sync || !sync->lock || !sync->unlock ||
        ep5_look_cache_init(&loader->cache, first, table_bytes, second, table_bytes) != EP5_LOOK_STOCK)
        return 0;
    loader->io = *io;
    loader->sync = *sync;
    ep5_lut_job_init(&loader->job);
    loader->medium = loader->job_medium = loader->shot = 0;
    loader->desired.amount_q8 = 0;
    loader->pinned = NULL;
    loader->running = loader->stepping = 0;
    invalidate(loader, EP5_LUT_JOB_STOCK);
    return 1;
}

void ep5_lut_preload_media(struct ep5_lut_preload *loader, uint32_t medium)
{
    loader->sync.lock(loader->sync.context);
    if (loader->medium != medium) {
        loader->medium = medium;
        loader->desired.amount_q8 = 0;
        invalidate(loader, EP5_LUT_JOB_STOCK);
    }
    loader->sync.unlock(loader->sync.context);
}

int ep5_lut_preload_select(struct ep5_lut_preload *loader, uint32_t medium,
                           const struct ep5_lut_menu_capture *choice)
{
    int accepted = 0;
    loader->sync.lock(loader->sync.context);
    if (medium && loader->medium == medium) {
        if (!choice || !choice->amount_q8) {
            loader->desired.amount_q8 = 0;
            invalidate(loader, EP5_LUT_JOB_STOCK);
            accepted = 1;
        } else if (choice->amount_q8 <= 256 && choice->number >= 1 && choice->number <= 16) {
            if ((loader->status != EP5_LUT_JOB_BUSY && loader->status != EP5_LUT_JOB_APPLY) ||
                !same_table(&loader->desired, choice))
                invalidate(loader, EP5_LUT_JOB_BUSY);
            loader->desired = *choice;
            if (loader->published.table)
                loader->published.amount_q8 = choice->amount_q8;
            accepted = 1;
        }
    }
    loader->sync.unlock(loader->sync.context);
    return accepted;
}

int ep5_lut_preload_step(struct ep5_lut_preload *loader)
{
    int result;
    loader->sync.lock(loader->sync.context);
    if (loader->stepping) {
        loader->sync.unlock(loader->sync.context);
        return EP5_LUT_JOB_BUSY;
    }
    if (!loader->running && loader->status == EP5_LUT_JOB_BUSY) {
        if (loader->pinned == loader->cache.staging) {
            loader->sync.unlock(loader->sync.context);
            return EP5_LUT_PRELOAD_WAIT_SHOT;
        }
        const struct ep5_look_io io = {loader, open_on_medium, read_on_medium, close_on_medium};
        loader->job_medium = loader->medium;
        if (ep5_lut_job_request(&loader->job, &io, &loader->cache,
                                loader->desired.picture_mode, loader->desired.variant, 1) &&
            ep5_lut_job_bind(&loader->job, loader->desired.number, loader->desired.look_crc,
                             loader->desired.amount_q8)) {
            loader->running = 1;
            loader->discard = 0;
        } else {
            invalidate(loader, EP5_LUT_JOB_ERROR);
        }
    }
    if (!loader->running) {
        result = loader->status;
        loader->sync.unlock(loader->sync.context);
        return result;
    }
    unsigned generation = loader->discard ? 0u : 1u;
    loader->stepping = 1;
    loader->sync.unlock(loader->sync.context);

    result = ep5_lut_job_step(&loader->job, generation);

    loader->sync.lock(loader->sync.context);
    loader->stepping = 0;
    if (result != EP5_LUT_JOB_BUSY) {
        loader->running = 0;
        if (!loader->discard) {
            loader->status = (uint8_t)result;
            if (result == EP5_LUT_JOB_APPLY) {
                loader->published = loader->job.result;
                loader->published.amount_q8 = loader->desired.amount_q8;
            }
        }
    }
    result = loader->running ? EP5_LUT_JOB_BUSY : loader->status;
    loader->sync.unlock(loader->sync.context);
    return result;
}

enum ep5_lut_job_status ep5_lut_preload_status(struct ep5_lut_preload *loader, uint32_t medium,
                                               const struct ep5_lut_menu_capture *choice)
{
    if (!loader || !medium || !choice) return EP5_LUT_JOB_IDLE;
    loader->sync.lock(loader->sync.context);
    enum ep5_lut_job_status result = EP5_LUT_JOB_IDLE;
    if (loader->medium == medium) {
        if (!choice->amount_q8) result = EP5_LUT_JOB_STOCK;
        else if (loader->desired.amount_q8 == choice->amount_q8 && same_table(&loader->desired, choice))
            result = loader->status;
    }
    loader->sync.unlock(loader->sync.context);
    return result;
}

int ep5_lut_preload_acquire(struct ep5_lut_preload *loader, uint32_t medium,
                            uint32_t shot, const struct ep5_lut_menu_capture *choice,
                            struct ep5_look_selection *selection)
{
    if (!selection)
        return 0;
    int acquired = 0;
    *selection = (struct ep5_look_selection){0};
    loader->sync.lock(loader->sync.context);
    if (shot && !loader->pinned && medium && medium == loader->medium &&
        loader->published.table && choice && same_table(&loader->desired, choice) &&
        choice->amount_q8 == loader->published.amount_q8) {
        *selection = loader->published;
        loader->pinned = selection->table;
        loader->shot = shot;
        acquired = 1;
    }
    loader->sync.unlock(loader->sync.context);
    return acquired;
}

int ep5_lut_preload_release(struct ep5_lut_preload *loader, uint32_t shot)
{
    int released = 0;
    loader->sync.lock(loader->sync.context);
    if (loader->pinned && shot == loader->shot) {
        loader->pinned = NULL;
        loader->shot = 0;
        released = 1;
    }
    loader->sync.unlock(loader->sync.context);
    return released;
}
