#include "lut.h"

static uint16_t lerp(uint16_t a, uint16_t b, unsigned fraction)
{
    /* a * (65535 - fraction) + b * fraction, with a single
     * variable multiply. Unsigned arithmetic also covers b < a. */
    uint32_t weighted = ((uint32_t)a << 16) - a +
                        ((uint32_t)b - a) * fraction + 32767u;
    /* Divide by 2^16-1. weighted <= 65535^2 + 32767, so the
     * correction cannot overflow. This keeps the original rounding. */
    return (uint16_t)((weighted + 1u + (weighted >> 16)) >> 16);
}

void ep5_lut_sample16(const uint16_t *lut, const uint16_t rgb[3], uint16_t out[3])
{
    unsigned cell[3], fraction[3];
    for (unsigned c = 0; c < 3; ++c) {
        /* Each of the 15 interior boundaries rounds up to a multiple of
         * 4096. At 65535 this also gives cell 15 with full upper weight. */
        cell[c] = rgb[c] >> 12;
        fraction[c] = ((rgb[c] & 4095u) << 4) + cell[c];
    }
    size_t at = ((cell[2] * 17u + cell[1]) * 17u + cell[0]) * 3u;
    for (unsigned c = 0; c < 3; ++c) {
        const uint16_t *p = lut + at + c;
        uint16_t low = lerp(lerp(p[0], p[3], fraction[0]),
                            lerp(p[51], p[54], fraction[0]), fraction[1]);
        uint16_t high = lerp(lerp(p[867], p[870], fraction[0]),
                             lerp(p[918], p[921], fraction[0]), fraction[1]);
        out[c] = lerp(low, high, fraction[2]);
    }
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
            uint16_t rgb[3], out[3];
            for (unsigned c = 0; c < 3; ++c) rgb[c] = (uint16_t)(pixel[c] * 257u);
            ep5_lut_sample16(lut, rgb, out);
            for (unsigned c = 0; c < 3; ++c) pixel[c] = (uint8_t)((out[c] + 128u) / 257u);
        }
    }
    return 0;
}
