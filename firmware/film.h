#ifndef EP5_FILM_H
#define EP5_FILM_H
#include "lut.h"

struct ep5_image {
    uint8_t *data;
    size_t capacity;
    uint32_t width, height;
    size_t stride;
};

#define EP5_BT601_FULL_YUYV 1u
#define EP5_FILM_INVALID (-1)
#define EP5_FILM_CANCELLED (-2)
#define EP5_FILM_DISCARD (-3)

/* No pointer is dereferenced from the descriptor; memory is an independently
 * acquired mapping. Format 0x302 as YUYV still needs confirmation on E-P5. */
int ep5_image_from_desc(struct ep5_image *out, const uint8_t *desc, size_t desc_bytes,
                        uint32_t mapped_address, uint8_t *memory, size_t capacity);

/* 0 permits encoding; DISCARD requires redeveloping/discarding this YCC buffer.
 * Return nonzero from progress to continue. Runs before processing and at most
 * every 16 rows; caller must establish exclusive ownership/cache and encoding.
 * LUT, descriptor, callback state and image must not overlap. No camera I/O. */
int ep5_film_apply(const struct ep5_image *image, const uint16_t *lut, size_t values,
                    unsigned encoding, unsigned amount,
                    int (*progress)(void *, uint32_t, uint32_t), void *context);
#endif
