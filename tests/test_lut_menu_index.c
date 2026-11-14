#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "lut_menu_index.h"

static uint8_t index_bytes[20 + 14 * 28];
static unsigned position;
static int close_count;

static uint32_t crc32(const uint8_t *bytes, unsigned count)
{
    uint32_t value = 0xffffffffu;
    while (count--) {
        value ^= *bytes++;
        for (unsigned bit = 0; bit < 8; ++bit)
            value = (value >> 1) ^ ((0u - (value & 1u)) & 0xedb88320u);
    }
    return value ^ 0xffffffffu;
}

static void put16(unsigned offset, uint16_t value)
{ index_bytes[offset] = (uint8_t)value; index_bytes[offset + 1] = (uint8_t)(value >> 8); }
static void put32(unsigned offset, uint32_t value)
{
    for (unsigned byte = 0; byte < 4; ++byte) index_bytes[offset + byte] = (uint8_t)(value >> (8 * byte));
}
static void make_index(void)
{
    static const uint16_t modes[] = {100, 101, 102, 103, 104, 105, 105, 105,
                                     106, 107, 108, 109, 119, 120};
    static const uint8_t variants[] = {1, 1, 1, 1, 1, 1, 2, 3,
                                       1, 1, 1, 1, 1, 1};
    memset(index_bytes, 0, sizeof index_bytes);
    memcpy(index_bytes, "EP5IDX02", 8);
    put16(8, 2); put16(10, 14); put32(12, 14 * 28);
    for (unsigned index = 0; index < 14; ++index) {
        unsigned offset = 20 + index * 28;
        put16(offset, modes[index]); index_bytes[offset + 2] = variants[index];
        index_bytes[offset + 3] = 1; put16(offset + 4, (uint16_t)(64 + index));
        put16(offset + 6, (uint16_t)(index + 1));
        for (unsigned unit = 0; unit < 8; ++unit) put16(offset + 12 + 2 * unit, unit == 0 ? (uint16_t)('A' + index) : 0);
    }
    put32(16, crc32(index_bytes + 20, 14 * 28));
}

static void *open_file(void *context, const char *path)
{ (void)context; assert(!strcmp(path, "EP5LUT/INDEX.EP5")); position = 0; return index_bytes; }
static int32_t read_file(void *context, void *file, uint8_t *destination, uint32_t count)
{
    (void)context; assert(file == index_bytes);
    if (position >= sizeof index_bytes) return 0;
    if (count > sizeof index_bytes - position) count = (uint32_t)(sizeof index_bytes - position);
    memcpy(destination, index_bytes + position, count); position += count; return (int32_t)count;
}
static int close_file(void *context, void *file)
{ (void)context; assert(file == index_bytes); ++close_count; return 0; }

int main(void)
{
    struct ep5_look_io io = {0, open_file, read_file, close_file};
    struct ep5_lut_menu menu;
    make_index(); ep5_lut_menu_init(&menu);
    assert(ep5_lut_menu_load_index(&io, &menu, 7) == 1);
    assert(menu.state == EP5_LUT_MENU_READY && menu.generation == 7 && close_count == 1);
    for (unsigned index = 0; index < EP5_LUT_MENU_SLOTS; ++index) {
        assert(menu.slots[index].configured && menu.slots[index].amount_q8 == 64 + index);
    }
    assert(menu.slots[5].label[0] == 'F' && menu.slots[11].label[0] == 'L');
    put16(20, 999);
    put32(16, crc32(index_bytes + 20, 14 * 28));
    assert(ep5_lut_menu_load_index(&io, &menu, 8) == 0 && menu.state == EP5_LUT_MENU_ERROR);
    make_index();
    index_bytes[20 + 2] = 4;
    put32(16, crc32(index_bytes + 20, 14 * 28));
    assert(ep5_lut_menu_load_index(&io, &menu, 8) == 0 && menu.state == EP5_LUT_MENU_ERROR);
    make_index();
    index_bytes[20 + 12] = 0; index_bytes[20 + 13] = 0;
    put32(16, crc32(index_bytes + 20, 14 * 28));
    assert(ep5_lut_menu_load_index(&io, &menu, 8) == 0 && menu.state == EP5_LUT_MENU_ERROR);
    return 0;
}
