/* Host-only exercise of diagnostic record safety and snapshot lifecycle. */
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "diag.h"

volatile uint32_t ep5_look_state[4];
uint8_t ep5_diag_bss_start[1], ep5_diag_bss_end[1];
static uint8_t file_bytes[EP5_DIAG_RECORD_BYTES * EP5_DIAG_MAX_RECORDS];
static unsigned file_size;
static int fail_write;

void *ep5_file_open(const char *path, const char *mode)
{
    assert(!strcmp(path, "EP5LUT/DIAG.LOG") && !strcmp(mode, "wb"));
    file_size = 0;
    return file_bytes;
}
int32_t ep5_file_write(const void *buffer, uint32_t size, uint32_t count, void *file)
{
    assert(file == file_bytes && size == 1);
    if (fail_write) return 0;
    assert(file_size + count <= sizeof file_bytes);
    memcpy(file_bytes + file_size, buffer, count);
    file_size += count;
    return (int32_t)count;
}
void ep5_file_close(void *file) { assert(file == file_bytes); }

static uint32_t get32(const uint8_t *p)
{ return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }

int main(void)
{
    uint8_t request[40] = {0};
    /* Invalid but previously admitted flash pointer; do not dereference it. */
    request[2] = 0x10; request[3] = 0x7e;
    assert(ep5_diag_observe(request, 0, 0) == 1);
    assert(ep5_diag_flush() == 128 && file_size == 128);
    assert(get32(file_bytes + 12) == 0x7e100000 && get32(file_bytes + 56) == 0);
    for (unsigned i = 33; i < 49; ++i) assert(file_bytes[i] == 0);
    request[0] = 0xff; request[1] = 0xff; request[2] = 0xff; request[3] = 0xff;
    assert(ep5_diag_observe(request, 0, 0) == 1);
    fail_write = 1;
    assert(ep5_diag_flush() < 0);
    fail_write = 0;
    assert(ep5_diag_flush() == 256 && file_size == 256);
    assert(get32(file_bytes + 4) == 0 && get32(file_bytes + 128 + 4) == 1);
    assert(get32(file_bytes + 128 + 12) == 0xffffffffu);
    for (unsigned i = 2; i < EP5_DIAG_MAX_RECORDS; ++i)
        assert(ep5_diag_observe(request, 0, 0) == 1);
    assert(ep5_diag_observe(request, 0, 0) == 0);
    assert(ep5_diag_flush() == (int32_t)sizeof file_bytes);
    return 0;
}
