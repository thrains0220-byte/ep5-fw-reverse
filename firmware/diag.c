/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "diag.h"

/* Stock file service (docs/FILE_SERVICE_MAP.md). The write veneer mirrors the
 * proven read veneer ABI: 4 args, ret [d2,d3,a2,a3],40. */
extern void *ep5_file_open(const char *path, const char *mode);
extern int32_t ep5_file_write(const void *buffer, uint32_t size, uint32_t count, void *file);
extern void ep5_file_close(void *file);

extern volatile uint32_t ep5_look_state[4];

/* Linker-provided .bss bounds (ep5_diag.ld defines _ep5_diag_bss_*; the C
 * compiler adds its own underscore prefix, so declare without one). */
extern uint8_t ep5_diag_bss_start[], ep5_diag_bss_end[];

static struct ep5_diag_record records[EP5_DIAG_MAX_RECORDS];
static uint32_t record_count;
static uint32_t sequence;
static uint32_t init_flag;

typedef char ep5_diag_record_size_check[
    (sizeof(struct ep5_diag_record) == EP5_DIAG_RECORD_BYTES) ? 1 : -1];

void ep5_diag_init(void)
{
    /* Flash erase pattern is 0xFF, so a fresh boot never matches the magic. */
    if (init_flag == EP5_DIAG_MAGIC)
        return;
    for (uint8_t *p = ep5_diag_bss_start; p < ep5_diag_bss_end; ++p)
        *p = 0;
    init_flag = EP5_DIAG_MAGIC;
}

static uint16_t rd16(const uint8_t *p)
{ return (uint16_t)((unsigned)p[0] | (unsigned)p[1] << 8); }
static uint32_t rd32(const uint8_t *p)
{ return (uint32_t)rd16(p) | (uint32_t)rd16(p + 2) << 16; }

/* Conservative buffer readability: a plausible RAM alias, not flash/code. */
static int readable(uint32_t a)
{
    uint32_t region = a >> 29;
    /* 0x6000_0000 (region 3) cached RAM and 0xa000_0000 (region 5) uncached
     * alias are the SDRAM windows used by the ART pool in the model. Reject
     * the flash/code region (0x7e1xxxxx) and null. */
    if (!a) return 0;
    if (region == 3 || region == 5 || (a >> 28) == 0x1u) return 1;
    return 0;
}

int ep5_diag_observe(const uint8_t *request, const void *context, uint32_t global_addr)
{
    struct ep5_diag_record *r;
    uint32_t buffer;
    if (!request || record_count >= EP5_DIAG_MAX_RECORDS)
        return 0;
    r = &records[record_count];
    for (unsigned i = 0; i < sizeof *r; ++i) ((uint8_t *)r)[i] = 0;
    r->magic = EP5_DIAG_MAGIC;
    r->seq = sequence++;
    r->jpeg_request = (uint32_t)(uintptr_t)request;
    buffer = rd32(request);
    r->buffer_addr = buffer;
    r->width = rd16(request + 4);
    r->height = rd16(request + 6);
    r->store_w = rd16(request + 8);
    r->store_h = rd16(request + 10);
    r->global_addr = global_addr;
    r->context = (uint32_t)(uintptr_t)context;
    r->fmt_byte36 = request[36];
    r->pool_ptr = ep5_look_state[3];
    if (readable(buffer)) {
        const uint8_t *p = (const uint8_t *)(uintptr_t)buffer;
        for (unsigned i = 0; i < 16; ++i) r->sample[i] = p[i];
        r->flags = 3;
    } else {
        r->flags = 0;
    }
    ++record_count;
    return 1;
}

static const char diag_path[] = "EP5LUT/DIAG.LOG";
static const char diag_wb[] = "wb";

static void put32(uint8_t *p, uint32_t v)
{ for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(v >> (8 * i)); }
static void put16le(uint8_t *p, uint16_t v)
{ p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }

/* Serialize explicitly: no struct padding or endianness assumptions on the
 * wire. Layout matches docs/DIAG_LOG_FORMAT.md. */
static void serialize(const struct ep5_diag_record *r, uint8_t *out)
{
    for (unsigned i = 0; i < EP5_DIAG_RECORD_BYTES; ++i) out[i] = 0;
    put32(out + 0, r->magic);
    put32(out + 4, r->seq);
    put32(out + 8, r->jpeg_request);
    put32(out + 12, r->buffer_addr);
    put16le(out + 16, r->width);
    put16le(out + 18, r->height);
    put16le(out + 20, r->store_w);
    put16le(out + 22, r->store_h);
    put32(out + 24, r->global_addr);
    put32(out + 28, r->context);
    out[32] = r->fmt_byte36;
    for (unsigned i = 0; i < 16; ++i) out[33 + i] = r->sample[i];
    put32(out + 52, r->pool_ptr);
    put32(out + 56, r->flags);
}

int32_t ep5_diag_flush(void)
{
    void *f;
    int32_t total = 0;
    uint8_t wire[EP5_DIAG_RECORD_BYTES];
    if (!record_count)
        return 0;
    f = ep5_file_open(diag_path, diag_wb);
    if (!f)
        return -1;
    for (uint32_t i = 0; i < record_count; ++i) {
        serialize(&records[i], wire);
        int32_t n = ep5_file_write(wire, 1, EP5_DIAG_RECORD_BYTES, f);
        if (n != (int32_t)EP5_DIAG_RECORD_BYTES) {
            ep5_file_close(f);
            return total ? total : -2;
        }
        total += n;
    }
    ep5_file_close(f);
    record_count = 0;
    return total;
}
