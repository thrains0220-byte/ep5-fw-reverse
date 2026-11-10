#include "film.h"

static uint16_t read16(const uint8_t *p)
{
    return (uint16_t)((unsigned)p[0] | (unsigned)p[1] << 8);
}

static uint32_t read32(const uint8_t *p)
{
    return (uint32_t)read16(p) | (uint32_t)read16(p + 2) << 16;
}

static int valid_image(const struct ep5_image *image)
{
    size_t row;
    if (!image || !image->data || !image->width || (image->width & 1u) || !image->height)
        return 0;
    row = (size_t)image->width * 2u;
    if (row / 2u != image->width || image->stride < row ||
        (size_t)(image->height - 1u) > (SIZE_MAX - row) / image->stride)
        return 0;
    return (size_t)(image->height - 1u) * image->stride + row <= image->capacity;
}

int ep5_image_from_desc(struct ep5_image *out, const uint8_t *desc, size_t desc_bytes,
                        uint32_t mapped_address, uint8_t *memory, size_t capacity)
{
    struct ep5_image image;
    uint32_t address, pitch, x, y, delta;
    size_t start;
    if (!out || !desc || desc_bytes < 32 || !memory ||
        !capacity || capacity - 1u > UINT32_MAX - mapped_address)
        return -1;
    address = read32(desc);
    pitch = read16(desc + 10);
    image.width = read16(desc + 12);
    image.height = read16(desc + 14);
    x = read16(desc + 20);
    y = read16(desc + 22);
    if (read32(desc + 4) || read16(desc + 8) != 0x302 || (x & 1u) ||
        x + image.width > pitch || address < mapped_address)
        return -1;
    delta = address - mapped_address;
    image.stride = (size_t)pitch * 2u;
    if (delta >= capacity || (size_t)y > (SIZE_MAX - delta) / (image.stride ? image.stride : 1u))
        return -1;
    start = (size_t)delta + y * image.stride;
    if ((size_t)x * 2u > SIZE_MAX - start) return -1;
    start += (size_t)x * 2u;
    if (start >= capacity) return -1;
    image.data = memory + start;
    image.capacity = capacity - start;
    if (!valid_image(&image)) return -1;
    *out = image;
    return 0;
}

static int32_t rounded(int32_t value, int32_t denominator)
{
    return value < 0 ? -((-value + denominator / 2) / denominator)
                     : (value + denominator / 2) / denominator;
}

static uint16_t clip16(int32_t v)
{
    return (uint16_t)(v < 0 ? 0 : v > 65535 ? 65535 : v);
}

static uint8_t changed(uint8_t original, int32_t delta)
{
    int32_t v = original + rounded(delta, 257);
    return (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v);
}

static void colour_delta(uint8_t y, int32_t cb, int32_t cr, const uint16_t *lut,
                         unsigned amount, int32_t delta[3])
{
    int32_t luma = (int32_t)y * 257;
    uint16_t rgb[3], out[3];
    rgb[0] = clip16(luma + rounded(22970 * cr, 16384));
    rgb[1] = clip16(luma - rounded(5638 * cb + 11700 * cr, 16384));
    rgb[2] = clip16(luma + rounded(29032 * cb, 16384));
    ep5_lut_sample16(lut, rgb, out);
    for (unsigned c = 0; c < 3; ++c)
        delta[c] = rounded(((int32_t)out[c] - rgb[c]) * (int32_t)amount, 256);
}

int ep5_film_apply(const struct ep5_image *image, const uint16_t *lut, size_t values,
                    unsigned encoding, unsigned amount,
                    int (*progress)(void *, uint32_t, uint32_t), void *context)
{
    if (!valid_image(image) || !lut || values != EP5_LUT_VALUES ||
        encoding != EP5_BT601_FULL_YUYV || amount > 256)
        return EP5_FILM_INVALID;
    if (progress && !progress(context, 0, image->height)) return EP5_FILM_CANCELLED;
    if (!amount) return 0;
    for (uint32_t y = 0; y < image->height; ++y) {
        uint8_t *p = image->data + (size_t)y * image->stride;
        for (uint32_t x = 0; x < image->width; x += 2, p += 4) {
            int32_t cb = ((int32_t)p[1] - 128) * 257;
            int32_t cr = ((int32_t)p[3] - 128) * 257;
            int32_t a[3], b[3], mean[3];
            colour_delta(p[0], cb, cr, lut, amount, a);
            colour_delta(p[2], cb, cr, lut, amount, b);
            for (unsigned c = 0; c < 3; ++c) mean[c] = rounded(a[c] + b[c], 2);
            p[0] = changed(p[0], rounded(4899 * a[0] + 9617 * a[1] + 1868 * a[2], 16384));
            p[2] = changed(p[2], rounded(4899 * b[0] + 9617 * b[1] + 1868 * b[2], 16384));
            /* Preserve the original YCC residual instead of clipping and
             * re-encoding its RGB reconstruction; identity remains byte-exact. */
            p[1] = changed(p[1], rounded(-2765 * mean[0] - 5427 * mean[1] + 8192 * mean[2], 16384));
            p[3] = changed(p[3], rounded(8192 * mean[0] - 6860 * mean[1] - 1332 * mean[2], 16384));
        }
        if (progress && (((y + 1u) % 16u == 0) || y + 1u == image->height) &&
            !progress(context, y + 1u, image->height))
            return EP5_FILM_DISCARD;
    }
    return 0;
}
