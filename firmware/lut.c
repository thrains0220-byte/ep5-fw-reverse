#include "lut.h"

static uint16_t lerp(uint16_t a, uint16_t b, unsigned fraction)
{
    return (uint16_t)(((uint32_t)a * (255u - fraction) +
                       (uint32_t)b * fraction + 127u) / 255u);
}

int ep5_lut_rgb8(uint8_t *pixels, size_t capacity, uint32_t width,
                 uint32_t height, size_t stride, const uint16_t *lut,
                 size_t values)
{
    size_t row_bytes, required;
    if (!pixels || !lut || !width || !height || values != EP5_LUT_VALUES)
        return -1;
    row_bytes = (size_t)width * 3u;
    if (row_bytes / 3u != width || stride < row_bytes)
        return -1;
    if ((size_t)(height - 1u) > (SIZE_MAX - row_bytes) / stride)
        return -1;
    required = (size_t)(height - 1u) * stride + row_bytes;
    if (required > capacity)
        return -1;

    for (uint32_t y = 0; y < height; ++y) {
        uint8_t *pixel = pixels + (size_t)y * stride;
        for (uint32_t x = 0; x < width; ++x, pixel += 3) {
            unsigned cell[3], fraction[3];
            for (unsigned c = 0; c < 3; ++c) {
                unsigned position = (unsigned)pixel[c] * 16u;
                cell[c] = position / 255u;
                fraction[c] = position % 255u;
                if (cell[c] == 16u) {
                    cell[c] = 15u;
                    fraction[c] = 255u;
                }
            }
            size_t at = ((cell[2] * 17u + cell[1]) * 17u + cell[0]) * 3u;
            for (unsigned c = 0; c < 3; ++c) {
                const uint16_t *p = lut + at + c;
                uint16_t low = lerp(lerp(p[0], p[3], fraction[0]),
                                    lerp(p[51], p[54], fraction[0]), fraction[1]);
                uint16_t high = lerp(lerp(p[867], p[870], fraction[0]),
                                     lerp(p[918], p[921], fraction[0]), fraction[1]);
                pixel[c] = (uint8_t)((lerp(low, high, fraction[2]) + 128u) / 257u);
            }
        }
    }
    return 0;
}
