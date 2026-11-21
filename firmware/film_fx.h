#ifndef EP5_FILM_FX_H
#define EP5_FILM_FX_H
#include "film.h"

enum ep5_film_halo_tint {
    EP5_FILM_HALO_WARM = 0, EP5_FILM_HALO_AMBER = 1, EP5_FILM_HALO_RED = 2
};

struct ep5_film_fx_settings {
    unsigned grain, halation, bloom; /* 0 through 100 */
    uint32_t seed;                   /* 0 is a valid seed */
    unsigned halo_tint;              /* EP5_FILM_HALO_* */
    unsigned clarity;                /* Contrast gain in percent */
};

/* Returns required bytes, or 0 for an invalid request or no scratch needed. */
size_t ep5_film_fx_scratch_bytes(uint32_t width,
                                const struct ep5_film_fx_settings *settings);

/* In-place full-range BT.601 YUYV. Scratch and other inputs must not overlap
 * the image or each other. Use the film.h ownership and encoding contract.
 * INVALID leaves the image untouched. CANCELLED leaves the image untouched.
 * DISCARD means processing was cancelled after writing rows. */
int ep5_film_fx_apply(const struct ep5_image *image, unsigned encoding,
                      const struct ep5_film_fx_settings *settings,
                      void *scratch, size_t scratch_bytes,
                      int (*progress)(void *, uint32_t, uint32_t), void *context);
#endif
