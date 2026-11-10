#ifndef EP5_LUT_H
#define EP5_LUT_H
#include <stddef.h>
#include <stdint.h>

#define EP5_LUT_SIDE 17u
#define EP5_LUT_VALUES (17u * 17u * 17u * 3u)

/* Internal sampler: caller validates table length and all three-word arrays. */
void ep5_lut_sample16(const uint16_t *lut, const uint16_t rgb[3], uint16_t out[3]);

/* Display-referred RGB8 in place; red-fastest RGB16 LUT, separate from pixels.
 * The camera adapter must establish colour space and buffer ownership first. */
int ep5_lut_rgb8(uint8_t *pixels, size_t capacity, uint32_t width,
                 uint32_t height, size_t stride, const uint16_t *lut,
                 size_t values);
#endif
