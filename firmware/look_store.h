#ifndef EP5_LOOK_STORE_H
#define EP5_LOOK_STORE_H
#include <stddef.h>
#include <stdint.h>
#include "lut.h"

/* Offline candidate, not a hook. Single owner: serialize calls, file changes,
 * and all consumers of returned table pointers. Neither reentrant nor ISR-safe.
 * A production adapter must ensure mount identity, cancellation and task lifetime.
 * Read is trusted to write no more than requested; 0 means confirmed clean EOF,
 * negative means error, including failure while checking EOF. Close: 0=success.
 * Paths are fixed ASCII names relative to a validated SD root. */
struct ep5_look_io {
    void *ctx;
    void *(*open)(void *ctx, const char *path);
    int32_t (*read)(void *ctx, void *file, uint8_t *dst, uint32_t count);
    int (*close)(void *ctx, void *file);
};
struct ep5_look_cache {
    uint16_t *active, *staging;
};
struct ep5_look_selection {
    const uint16_t *table;
    uint16_t amount_q8, number;
};
enum ep5_look_result { EP5_LOOK_BAD=-1, EP5_LOOK_STOCK=0, EP5_LOOK_APPLY=1 };

/* Two aligned nonoverlapping writable arrays owned by the caller for the whole
 * session. Capacities in bytes. Control structures must not alias these arrays
 * or one another. No heap allocation, fixed addresses or flash writes. */
int ep5_look_cache_init(struct ep5_look_cache *cache, void *a, size_t a_bytes,
                        void *b, size_t b_bytes);
/* Rereads the index on each explicit load. Missing slot or zero strength =
 * STOCK; invalid or missing file = BAD. Both require stock rendering for this
 * request, leave the old cache untouched and clear selection. Only APPLY yields
 * a table. Never use a returned table across further loads without an owner lock. */
int ep5_look_load(const struct ep5_look_io *io, struct ep5_look_cache *cache,
                  uint16_t picture_mode, uint8_t variant,
                  struct ep5_look_selection *selection);
#endif
