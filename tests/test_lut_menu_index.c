#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "lut_menu_index.h"

static uint8_t index_bytes[20 + 3 * 28];
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
    memset(index_bytes, 0, sizeof index_bytes);
    memcpy(index_bytes, "EP5IDX02", 8);
    put16(8, 2); put16(10, 3); put32(12, 3 * 28);
    for (unsigned index = 0; index < 3; ++index) {
        unsigned offset = 20 + index * 28;
        put16(offset, 105); index_bytes[offset + 2] = (uint8_t)(index + 1);
        index_bytes[offset + 3] = 1; put16(offset + 4, (uint16_t)(64 + index));
        put16(offset + 6, (uint16_t)(index + 1));
        for (unsigned unit = 0; unit < 8; ++unit) put16(offset + 12 + 2 * unit, unit == 0 ? (uint16_t)('A' + index) : 0);
    }
    put32(16, crc32(index_bytes + 20, 3 * 28));
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
    assert(menu.slots[0].configured && menu.slots[0].amount_q8 == 64 && menu.slots[0].label[0] == 'A');
    assert(menu.slots[2].configured && menu.slots[2].amount_q8 == 66 && menu.slots[2].label[0] == 'C');
    index_bytes[20 + 12] = 0; index_bytes[20 + 13] = 0;
    put32(16, crc32(index_bytes + 20, 3 * 28));
    assert(ep5_lut_menu_load_index(&io, &menu, 8) == 0 && menu.state == EP5_LUT_MENU_ERROR);
    return 0;
}
