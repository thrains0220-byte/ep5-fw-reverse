#include "film_fx.h"

#define LIGHT_RADIUS 4u
#define LIGHT_ROWS (2u * LIGHT_RADIUS + 1u)
#define LIGHT_WEIGHT 25u
#define CLARITY_ROWS (LIGHT_ROWS + 1u)
#define CLARITY_COLUMNS 96u
#define MAX_CLARITY_STEP 64u

static int valid_settings(const struct ep5_film_fx_settings *settings)
{
    return settings && settings->grain <= 100u && settings->halation <= 100u &&
           settings->bloom <= 100u && settings->clarity <= 100u &&
           settings->halo_tint <= EP5_FILM_HALO_RED;
}

static int valid_width(uint32_t width)
{
    return width && !(width & 1u);
}

static uint32_t clarity_step(uint32_t width)
{
    uint32_t step = (width - 1u) / CLARITY_COLUMNS + 1u;
    return step > MAX_CLARITY_STEP ? MAX_CLARITY_STEP : step;
}

size_t ep5_film_fx_scratch_bytes(uint32_t width,
                                const struct ep5_film_fx_settings *settings)
{
    size_t bytes = 0;
    if (!valid_width(width) || !valid_settings(settings)) return 0;
    if (settings->halation || settings->bloom) {
        bytes = (size_t)width * LIGHT_ROWS;
        if (bytes / LIGHT_ROWS != width) return 0;
    }
    if (settings->clarity) {
        uint32_t cols = (width - 1u) / clarity_step(width) + 1u;
        size_t clarity_bytes = (size_t)cols * (CLARITY_ROWS + 1u);
        if (clarity_bytes / (CLARITY_ROWS + 1u) != cols || SIZE_MAX - bytes < clarity_bytes)
            return 0;
        bytes += clarity_bytes;
    }
    return bytes;
}

static uint32_t offset_pixel(uint32_t center, int offset, uint32_t length)
{
    if (offset < 0)
        return center < (unsigned)-offset ? 0 : center - (unsigned)-offset;
    return length - center <= (unsigned)offset ? length - 1u : center + (unsigned)offset;
}

static unsigned highlight(unsigned y)
{
    return y > 192u ? (y - 192u) * 4u : 0u;
}

static unsigned row_sample(const uint8_t *row, uint32_t x, int offset, uint32_t width,
                           int highlights)
{
    size_t index = offset_pixel(x, offset, width);
    return highlights ? highlight(row[2u * index]) : row[index];
}

static uint8_t *light_row(uint8_t *ring, uint32_t width, uint32_t y)
{
    return ring + (size_t)(y % LIGHT_ROWS) * width;
}

/* A sliding tent filter with weights 1, 2, 3, 4, 5, 4, 3, 2, 1.
 * Moving right removes one copy of the five left samples and adds one
 * copy of the five samples on the right. Extend the edge sample. */
static void prepare_tent(const uint8_t *row, uint8_t *out, uint32_t width, int highlights)
{
    const int radius = (int)LIGHT_RADIUS;
    unsigned total = 0, left = 0, right = 0;

    for (int k = -radius; k <= radius + 1; ++k) {
        unsigned light = row_sample(row, 0, k, width, highlights);
        if (k <= radius)
            total += light * (unsigned)(radius + 1 - (k < 0 ? -k : k));
        if (k <= 0)
            left += light;
        else
            right += light;
    }
    for (uint32_t x = 0; x < width - 1u; ++x) {
        unsigned next = row_sample(row, x, 1, width, highlights);
        out[x] = (uint8_t)((total + LIGHT_WEIGHT / 2u) / LIGHT_WEIGHT);
        total = total - left + right;
        left = left - row_sample(row, x, -radius, width, highlights) + next;
        right = right - next + row_sample(row, x, radius + 2, width, highlights);
    }
    out[width - 1u] = (uint8_t)((total + LIGHT_WEIGHT / 2u) / LIGHT_WEIGHT);
}

static void prepare_light(const struct ep5_image *image, uint8_t *ring, uint32_t y)
{
    prepare_tent(image->data + (size_t)y * image->stride, light_row(ring, image->width, y),
                 image->width, 1);
}

static unsigned spread_light(const uint8_t *const rows[LIGHT_ROWS], uint32_t x)
{
    unsigned total = rows[0][x] + rows[8][x] + 2u * (rows[1][x] + rows[7][x]) +
                     3u * (rows[2][x] + rows[6][x]) + 4u * (rows[3][x] + rows[5][x]) +
                     5u * rows[4][x];
    return (total + LIGHT_WEIGHT / 2u) / LIGHT_WEIGHT;
}

static uint8_t clip(int value)
{
    return (uint8_t)(value < 0 ? 0 : value > 255 ? 255 : value);
}

struct clarity_grid {
    uint8_t *ring, *row;
    uint32_t step, cols, rows, prepared;
};

static uint32_t min_u32(uint32_t a, uint32_t b)
{
    return a < b ? a : b;
}

/* Downsample the original luma with block averages. Keep only the coarse
 * rows required for a tent filter and interpolation between sample centers. */
static void make_clarity_row(const struct ep5_image *image, struct clarity_grid *g)
{
    uint32_t top = g->prepared * g->step;
    uint32_t height = min_u32(image->height - top, g->step);
    for (uint32_t col = 0; col < g->cols; ++col) {
        uint32_t left = col * g->step;
        uint32_t width = min_u32(image->width - left, g->step);
        uint32_t sum = 0, count = width * height;
        for (uint32_t y = 0; y < height; ++y) {
            const uint8_t *p = image->data + (size_t)(top + y) * image->stride + 2u * (size_t)left;
            for (uint32_t x = 0; x < width; ++x) sum += p[2u * x];
        }
        g->row[col] = (uint8_t)((sum + count / 2u) / count);
    }
    uint8_t *dest = g->ring + (size_t)(g->prepared % CLARITY_ROWS) * g->cols;
    prepare_tent(g->row, dest, g->cols, 0);
    ++g->prepared;
}

static unsigned interpolate(unsigned a, unsigned b, unsigned weight, unsigned step)
{
    return (a * (step - weight) + b * weight + step / 2u) / step;
}

static void build_clarity_field(const struct ep5_image *image, struct clarity_grid *g, uint32_t y)
{
    uint32_t centered = y < g->step / 2u ? 0 : y - g->step / 2u;
    uint32_t first = centered / g->step;
    uint32_t second = min_u32(first + 1u, g->rows - 1u);
    uint32_t required = second + min_u32(g->rows - 1u - second, LIGHT_RADIUS);
    const uint8_t *near_rows[LIGHT_ROWS], *far_rows[LIGHT_ROWS];
    while (g->prepared <= required)
        make_clarity_row(image, g);
    for (unsigned k = 0; k < LIGHT_ROWS; ++k) {
        int offset = (int)k - (int)LIGHT_RADIUS;
        uint32_t a = offset_pixel(first, offset, g->rows);
        uint32_t b = offset_pixel(second, offset, g->rows);
        near_rows[k] = g->ring + (size_t)(a % CLARITY_ROWS) * g->cols;
        far_rows[k] = g->ring + (size_t)(b % CLARITY_ROWS) * g->cols;
    }
    for (uint32_t x = 0; x < g->cols; ++x)
        g->row[x] = (uint8_t)interpolate(spread_light(near_rows, x), spread_light(far_rows, x),
                                         centered % g->step, g->step);
}

static int clarity_delta(const struct clarity_grid *g, uint32_t x, unsigned y, unsigned amount)
{
    uint32_t centered = x < g->step / 2u ? 0 : x - g->step / 2u;
    uint32_t first = centered / g->step;
    unsigned blur = interpolate(g->row[first], g->row[min_u32(first + 1u, g->cols - 1u)],
                                centered % g->step, g->step);
    int detail = (int)y - (int)blur;
    unsigned midtone = y < 128u ? y : 255u - y;
    const uint32_t scale = 25500u;
    unsigned magnitude = (unsigned)(((uint32_t)(detail < 0 ? -detail : detail) *
                                     amount * (128u + midtone) + scale / 2u) / scale);
    return detail < 0 ? -(int)magnitude : (int)magnitude;
}

static unsigned bloom_lift(unsigned y, unsigned field, unsigned amount)
{
    const uint32_t scale = 100u * 255u * 3u;
    return (unsigned)(((uint32_t)field * (255u - y) * amount + scale / 2u) / scale);
}

static unsigned halo_strength(unsigned y, unsigned field, unsigned amount)
{
    const uint32_t scale = 100u * 255u;
    return (unsigned)(((uint32_t)field * (255u - highlight(y)) * amount +
                      scale / 2u) / scale);
}

static void tint_halo(uint8_t *pair, unsigned halo, unsigned tint)
{
    /* Denominators for a negative Cb and positive Cr offset. */
    static const uint8_t cb[] = {24, 10, 36}, cr[] = {10, 13, 7};
    pair[1] = clip(pair[1] - (int)((halo + cb[tint] / 2u) / cb[tint]));
    pair[3] = clip(pair[3] + (int)((halo + cr[tint] / 2u) / cr[tint]));
}

static uint8_t add_grain(uint8_t y, unsigned amount, uint32_t *state)
{
    const uint32_t scale = 204000u;
    unsigned headroom = y < 128u ? y : 255u - y;
    int noise;
    uint32_t magnitude;

    /* A full-period generator also accepts zero. Two bytes give a
     * triangular distribution with less energy in the strongest changes. */
    *state = *state * UINT32_C(1664525) + UINT32_C(1013904223);
    noise = (int)(*state >> 24) - (int)((*state >> 16) & 255u);
    if (headroom > 96u) headroom = 96u;
    magnitude = ((uint32_t)(noise < 0 ? -noise : noise) * headroom * amount +
                 scale / 2u) / scale;
    return (uint8_t)(noise < 0 ? y - magnitude : y + magnitude);
}

int ep5_film_fx_apply(const struct ep5_image *image, unsigned encoding,
                      const struct ep5_film_fx_settings *settings,
                      void *scratch, size_t scratch_bytes,
                      int (*progress)(void *, uint32_t, uint32_t), void *context)
{
    uint32_t grain_state;
    uint8_t *ring = scratch;
    struct clarity_grid clarity = {0};
    int spatial_light;

    if (!ep5_image_valid(image) || !valid_settings(settings) || encoding != EP5_BT601_FULL_YUYV)
        return EP5_FILM_INVALID;
    spatial_light = settings->halation || settings->bloom;
    if (spatial_light || settings->clarity) {
        size_t required = ep5_film_fx_scratch_bytes(image->width, settings);
        if (!required || !ring || scratch_bytes < required) return EP5_FILM_INVALID;
    }
    if (progress && !progress(context, 0, image->height)) return EP5_FILM_CANCELLED;
    if (!spatial_light && !settings->grain && !settings->clarity) return 0;
    grain_state = settings->seed;
    if (settings->clarity) {
        clarity.step = clarity_step(image->width);
        clarity.cols = (image->width - 1u) / clarity.step + 1u;
        clarity.rows = (image->height - 1u) / clarity.step + 1u;
        clarity.ring = ring + (spatial_light ? (size_t)image->width * LIGHT_ROWS : 0u);
        clarity.row = clarity.ring + (size_t)clarity.cols * CLARITY_ROWS;
    }
    if (spatial_light) {
        for (uint32_t y = 0; y < image->height && y <= LIGHT_RADIUS; ++y)
            prepare_light(image, ring, y);
    }
    for (uint32_t y = 0; y < image->height; ++y) {
        const uint8_t *rows[LIGHT_ROWS];
        uint8_t *p = image->data + (size_t)y * image->stride;
        if (spatial_light) {
            for (unsigned k = 0; k < LIGHT_ROWS; ++k) {
                uint32_t sample = offset_pixel(y, (int)k - (int)LIGHT_RADIUS, image->height);
                rows[k] = light_row(ring, image->width, sample);
            }
        }
        if (settings->clarity) build_clarity_field(image, &clarity, y);
        for (uint32_t x = 0; x < image->width; x += 2, p += 4) {
            int delta_a = 0, delta_b = 0;
            if (settings->clarity) {
                delta_a = clarity_delta(&clarity, x, p[0], settings->clarity);
                delta_b = clarity_delta(&clarity, x + 1u, p[2], settings->clarity);
            }
            if (spatial_light) {
                unsigned field_a = spread_light(rows, x);
                unsigned field_b = spread_light(rows, x + 1u);
                unsigned halo_a = halo_strength(p[0], field_a, settings->halation);
                unsigned halo_b = halo_strength(p[2], field_b, settings->halation);
                unsigned halo = (halo_a + halo_b + 1u) / 2u;
                delta_a += (int)bloom_lift(p[0], field_a, settings->bloom) + (int)((halo_a + 8u) / 16u);
                delta_b += (int)bloom_lift(p[2], field_b, settings->bloom) + (int)((halo_b + 8u) / 16u);
                if (halo) tint_halo(p, halo, settings->halo_tint);
            }
            p[0] = clip(p[0] + delta_a);
            p[2] = clip(p[2] + delta_b);
            if (settings->grain) {
                p[0] = add_grain(p[0], settings->grain, &grain_state);
                p[2] = add_grain(p[2], settings->grain, &grain_state);
            }
        }
        if (progress && (((y + 1u) % 16u == 0) || y + 1u == image->height) &&
            !progress(context, y + 1u, image->height))
            return EP5_FILM_DISCARD;
        if (spatial_light && LIGHT_RADIUS < image->height - 1u - y)
            prepare_light(image, ring, y + LIGHT_RADIUS + 1u);
    }
    return 0;
}
