#ifndef EP5_LUT_JOB_H
#define EP5_LUT_JOB_H

#include "look_store.h"

/* Offline, single-owner worker state. All calls (including request/cancel and
 * access to cache/selection) must be serialized by the caller; no atomics or
 * camera task adapter is implied. The UI may copy a request to a worker queue,
 * but must never call step from its event/draw callback. A read/close may block
 * in the supplied backend despite the bounded amount of work in each step. */
#define EP5_LUT_JOB_CHUNK 512u

enum ep5_lut_job_status {
    EP5_LUT_JOB_IDLE = 0, EP5_LUT_JOB_BUSY = 1,
    EP5_LUT_JOB_APPLY = 2, EP5_LUT_JOB_STOCK = 3,
    EP5_LUT_JOB_ERROR = 4, EP5_LUT_JOB_CANCELLED = 5
};

struct ep5_lut_job {
    struct ep5_look_io io;
    struct ep5_look_cache *cache;
    void *file;
    uint32_t crc, expected_crc, bytes, slot_seen, number_seen;
    uint32_t look_crc[16];
    uint32_t bound_crc;
    uint16_t generation, picture_mode, amount, number, rows, row_index;
    uint16_t bound_number, bound_amount;
    uint8_t variant, state, target, status, after_close;
    uint8_t scratch[28];
    struct ep5_look_selection result;
};

/* Caller must supply a valid disjoint cache from ep5_look_cache_init and keep
 * it and the IO context alive until completion. Does not access a file. A busy
 * job cannot be replaced: change the generation passed to step to cancel it,
 * wait for CANCELLED, then submit a fresh request. Unsupported slots produce
 * STOCK without opening a file. Generation zero is reserved. */
int ep5_lut_job_request(struct ep5_lut_job *job, const struct ep5_look_io *io,
                        struct ep5_look_cache *cache, uint16_t picture_mode,
                        uint8_t variant, uint16_t generation);
int ep5_lut_job_bind(struct ep5_lut_job *job, uint16_t number, uint32_t crc,
                     uint16_t amount);
/* Initialize before first request. Only call when no file is open. */
void ep5_lut_job_init(struct ep5_lut_job *job);
/* One call performs at most one open/read/close, reads <= 512 bytes, and
 * performs <= 512 bytes CRC/conversion. Generation mismatch requests cleanup;
 * the worker keeps calling until CANCELLED (including one close if needed). */
int ep5_lut_job_step(struct ep5_lut_job *job, uint16_t current_generation);
/* Returns APPLY only for the still-current completed job, otherwise returns
 * STOCK/ERROR/CANCELLED/BUSY and clears output; does not transfer ownership.
 * Consumers must serialize usage with any further jobs and card changes. */
int ep5_lut_job_result(const struct ep5_lut_job *job, uint16_t current_generation,
                       struct ep5_look_selection *out);
#endif
