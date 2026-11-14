#include "lut_menu_index.h"

#define INDEX_HEADER 20u
#define INDEX_ROW 28u
#define INDEX_MAX_ROWS 32u
#define INDEX_PATH "EP5LUT/INDEX.EP5"

static uint16_t u16(const uint8_t *p)
{ return (uint16_t)p[0] | (uint16_t)p[1] << 8; }
static uint32_t u32(const uint8_t *p)
{ return (uint32_t)u16(p) | (uint32_t)u16(p + 2) << 16; }
static uint32_t crc_step(uint32_t crc, const uint8_t *p, uint32_t count)
{
    while (count--) {
        crc ^= *p++;
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ ((0u - (crc & 1u)) & 0xedb88320u);
    }
    return crc;
}
static int exact(const struct ep5_look_io *io, void *file, uint8_t *dst, uint32_t count)
{ return io->read(io->ctx, file, dst, count) == (int32_t)count; }
static int eof(const struct ep5_look_io *io, void *file)
{ uint8_t byte; return io->read(io->ctx, file, &byte, 1) == 0; }
static int label_ok(const uint8_t *label)
{
    unsigned count = 0;
    uint16_t last = 0;
    while (count < 8) {
        uint16_t code = u16(label + 2 * count);
        if (!code) break;
        if (code < 32 || (code >= 127 && code <= 159) ||
            (code >= 0xd800 && code <= 0xdfff) || code == 0xfffe || code == 0xffff ||
            (!count && code == 32)) return 0;
        last = code;
        ++count;
    }
    if (!count || last == 32) return 0;
    for (; count < 8; ++count)
        if (u16(label + 2 * count)) return 0;
    return 1;
}
static int target_slot(uint16_t mode, uint8_t variant)
{
    if (mode != 105 || variant < 1 || variant > 3) return -1;
    return (int)variant - 1;
}

int ep5_lut_menu_load_index(const struct ep5_look_io *io,
                            struct ep5_lut_menu *menu, uint16_t generation)
{
    struct ep5_lut_menu_slot next[EP5_LUT_MENU_SLOTS];
    uint8_t header[INDEX_HEADER], row[INDEX_ROW];
    uint32_t crc = 0xffffffffu;
    uint32_t expected_crc;
    void *file;
    unsigned count;
    if (!io || !io->open || !io->read || !io->close || !menu || !generation)
        return 0;
    for (unsigned index = 0; index < EP5_LUT_MENU_SLOTS; ++index) {
        next[index].picture_mode = 105;
        next[index].variant = (uint8_t)(index + 1);
        next[index].configured = 0;
        next[index].amount_q8 = 0;
        next[index].number = 0;
        for (unsigned unit = 0; unit < EP5_LUT_MENU_LABEL_UNITS; ++unit)
            next[index].label[unit] = 0;
    }
    if (!ep5_lut_menu_begin_load(menu, generation)) return 0;
    file = io->open(io->ctx, INDEX_PATH);
    if (!file) { (void)ep5_lut_menu_fail(menu, generation); return 0; }
    if (!exact(io, file, header, sizeof header) ||
        header[0] != 'E' || header[1] != 'P' || header[2] != '5' ||
        header[3] != 'I' || header[4] != 'D' || header[5] != 'X' ||
        header[6] != '0' || header[7] != '2' || u16(header + 8) != 2) {
        (void)io->close(io->ctx, file); (void)ep5_lut_menu_fail(menu, generation); return 0;
    }
    count = u16(header + 10);
    if (!count || count > INDEX_MAX_ROWS || u32(header + 12) != count * INDEX_ROW) {
        (void)io->close(io->ctx, file); (void)ep5_lut_menu_fail(menu, generation); return 0;
    }
    for (unsigned index = 0; index < count; ++index) {
        int target;
        if (!exact(io, file, row, sizeof row)) {
            (void)io->close(io->ctx, file); (void)ep5_lut_menu_fail(menu, generation); return 0;
        }
        crc = crc_step(crc, row, sizeof row);
        target = target_slot(u16(row), row[2]);
        if (row[3] != 1 || u16(row + 4) > 256 || u16(row + 6) < 1 ||
            u16(row + 6) > 16 || !label_ok(row + 12)) {
            (void)io->close(io->ctx, file); (void)ep5_lut_menu_fail(menu, generation); return 0;
        }
        if (target >= 0) {
            if (next[target].configured) {
                (void)io->close(io->ctx, file); (void)ep5_lut_menu_fail(menu, generation); return 0;
            }
            next[target].configured = 1;
            next[target].amount_q8 = u16(row + 4);
            next[target].number = u16(row + 6);
            for (unsigned unit = 0; unit < 8; ++unit)
                next[target].label[unit] = u16(row + 12 + 2 * unit);
        }
    }
    expected_crc = u32(header + 16);
    if ((crc ^ 0xffffffffu) != expected_crc || !eof(io, file) || io->close(io->ctx, file) != 0) {
        (void)ep5_lut_menu_fail(menu, generation); return 0;
    }
    return ep5_lut_menu_publish(menu, generation, next);
}
