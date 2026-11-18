#include "lut_menu_index.h"

int ep5_lut_menu_finish_index(const struct ep5_lut_job *job, struct ep5_lut_menu *menu)
{
    if (!job || !job->index_slots || !menu)
        return 0;
    struct ep5_look_selection unused;
    int status = ep5_lut_job_result(job, menu->generation, &unused);
    if (status == EP5_LUT_JOB_INDEX_READY)
        return ep5_lut_menu_publish(menu, job->generation, job->index_slots);
    if (status == EP5_LUT_JOB_ERROR)
        (void)ep5_lut_menu_fail(menu, job->generation);
    return 0;
}

int ep5_lut_menu_load_index(const struct ep5_look_io *io,
                            struct ep5_lut_menu *menu, uint16_t generation)
{
    struct ep5_lut_menu_slot staging[EP5_LUT_MENU_SLOTS];
    struct ep5_lut_job job;
    ep5_lut_job_init(&job);
    if (!menu || !ep5_lut_job_request_index(&job, io, staging, generation))
        return 0;
    (void)ep5_lut_menu_begin_load(menu, generation);
    while (ep5_lut_job_step(&job, generation) == EP5_LUT_JOB_BUSY) {
        /* Compatibility helper for callers that already own the file task. */
    }
    return ep5_lut_menu_finish_index(&job, menu);
}
