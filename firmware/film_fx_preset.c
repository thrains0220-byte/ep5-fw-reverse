/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "film_fx_preset.h"
#include "object_bytes.h"

#define HEADER_BYTES 20u
#define ROW_BYTES 16u

static uint16_t get16(const uint8_t *p)
{
    return (uint16_t)(p[0] | (uint16_t)p[1] << 8);
}

static uint32_t get32(const uint8_t *p)
{
    return get16(p) | (uint32_t)get16(p + 2) << 16;
}

static uint32_t crc32(const uint8_t *p, size_t n)
{
    uint32_t crc = UINT32_MAX;
    while (n--) {
        crc ^= *p++;
        for (unsigned bit = 0; bit < 8u; ++bit)
            crc = (crc >> 1) ^ ((0u - (crc & 1u)) & UINT32_C(0xedb88320));
    }
    return crc ^ UINT32_MAX;
}

static int valid_slot(uint16_t mode, uint8_t variant)
{
    if (mode == 105u) return variant >= 1u && variant <= 3u;
    return variant == 1u && ((mode >= 100u && mode <= 109u) || mode == 119u || mode == 120u);
}

int ep5_film_fx_preset(const uint8_t *data, size_t bytes,
                       const struct ep5_lut_menu_capture *choice, uint32_t seed,
                       struct ep5_film_fx_settings *out)
{
    const uint8_t *record = NULL;
    unsigned count, version;
    if (!out) return -1;
    ep5_zero_bytes(out, sizeof *out);
    out->seed = seed;
    if (!choice || !valid_slot(choice->picture_mode, choice->variant) ||
        choice->number < 1u || choice->number > 16u || choice->amount_q8 > 256u)
        return -1;
    if (!data) return bytes ? -1 : 0;
    if (bytes < HEADER_BYTES || bytes > EP5_FILM_FX_PRESET_MAX_BYTES) return -1;
    version = get16(data + 8);
    if (version != 1u && version != 2u) return -1;
    for (unsigned i = 0; i < 7u; ++i)
        if (data[i] != (uint8_t)"EP5FXP0"[i]) return -1;
    if (data[7] != '0' + version) return -1;
    count = get16(data + 10);
    if (!count || count > EP5_LUT_MENU_SLOTS ||
        bytes != HEADER_BYTES + count * ROW_BYTES ||
        get32(data + 12) != bytes - HEADER_BYTES ||
        get32(data + 16) != crc32(data + HEADER_BYTES, bytes - HEADER_BYTES))
        return -1;

    const uint8_t *first = data + HEADER_BYTES;
    const uint8_t *p = first;
    for (unsigned i = 0; i < count; ++i, p += ROW_BYTES) {
        uint16_t mode = get16(p);
        uint16_t number = get16(p + 4);
        uint32_t crc = get32(p + 8);
        if (!valid_slot(mode, p[2]) || p[3] > (version == 1u ? 0u : 100u) ||
            number < 1u || number > 16u ||
            get16(p + 6) || p[12] > 100u || p[13] > 100u || p[14] > 100u ||
            p[15] > EP5_FILM_HALO_RED)
            return -1;
        for (const uint8_t *q = first; q < p; q += ROW_BYTES) {
            if ((get16(q) == mode && q[2] == p[2]) ||
                (get16(q + 4) == number && get32(q + 8) != crc))
                return -1;
        }
        if (mode == choice->picture_mode && p[2] == choice->variant &&
            number == choice->number && crc == choice->look_crc)
            record = p;
    }
    if (!record) return 0;
    out->grain = record[12];
    out->halation = record[13];
    out->bloom = record[14];
    out->halo_tint = record[15];
    out->clarity = record[3];
    return 1;
}

int ep5_film_fx_preset_load(const struct ep5_look_io *io,
                            const struct ep5_lut_menu_capture *choice, uint32_t seed,
                            struct ep5_film_fx_settings *out)
{
    uint8_t data[EP5_FILM_FX_PRESET_MAX_BYTES + 1u];
    size_t bytes = 0;
    void *file;
    int32_t got;
    if (ep5_film_fx_preset(NULL, 0, choice, seed, out) != 0 ||
        !io || !io->open || !io->read || !io->close)
        return -1;
    file = io->open(io->ctx, EP5_FILM_FX_PRESET_PATH);
    if (!file) return 0;
    do {
        uint32_t capacity = (uint32_t)(sizeof data - bytes);
        got = io->read(io->ctx, file, data + bytes, capacity);
        if (got > (int32_t)capacity) got = -1;
        if (got > 0) bytes += (size_t)got;
    } while (got > 0 && bytes < sizeof data);
    if (io->close(io->ctx, file) || got != 0) return -1;
    return ep5_film_fx_preset(data, bytes, choice, seed, out);
}
