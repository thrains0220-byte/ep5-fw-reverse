/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "lut_job.h"

#define TABLE_BYTES (2u * EP5_LUT_VALUES)
#define ROW_BYTES 28u

enum state {
    OPEN_INDEX, INDEX_HEADER, INDEX_ROW, INDEX_EOF, CLOSE_INDEX,
    OPEN_TABLE, TABLE_HEADER, TABLE_DATA, TABLE_EOF, CLOSE_TABLE,
    CONVERT, COMMIT, CLEANUP, TERMINAL
};

static uint16_t u16(const uint8_t *p)
{ return (uint16_t)(p[0] | ((uint16_t)p[1] << 8)); }
static uint32_t u32(const uint8_t *p)
{ return u16(p) | ((uint32_t)u16(p + 2) << 16); }
static int magic(const uint8_t *p, const char *s)
{ for (unsigned i = 0; i < 8; ++i) if (p[i] != (uint8_t)s[i]) return 0; return 1; }
static uint32_t crc_step(uint32_t c, const uint8_t *p, unsigned n)
{
    while (n--) {
        c ^= *p++;
        for (unsigned i = 0; i < 8; ++i)
            c = (c >> 1) ^ ((0u - (c & 1u)) & 0xedb88320u);
    }
    return c;
}
static int slot(uint16_t mode, uint8_t variant)
{
    if (mode == 105) {
        if (variant < 1 || variant > 3) return -1;
        return 4 + variant;
    }
    if (variant != 1) return -1;
    switch (mode) {
    case 100: return 0; case 101: return 1; case 102: return 2;
    case 103: return 3; case 104: return 4; case 106: return 8;
    case 107: return 9; case 108: return 10; case 109: return 11;
    case 119: return 12; case 120: return 13; default: return -1;
    }
}
static int label_ok(const uint8_t *p)
{
    unsigned n = 0; uint16_t last = 0;
    while (n < 8) {
        uint16_t c = u16(p + 2 * n);
        if (!c) break;
        if (n >= 6 || c < 32 || (c >= 127 && c <= 159) ||
            (c >= 0xd800 && c <= 0xdfff) || c == 0xfffe || c == 0xffff ||
            (!n && c == 32)) return 0;
        last = c; ++n;
    }
    if (!n || last == 32) return 0;
    for (; n < 8; ++n) if (u16(p + 2 * n)) return 0;
    return 1;
}
static void finish(struct ep5_lut_job *j, int status)
{
    j->result.table = 0; j->result.amount_q8 = j->result.number = 0; j->result.look_crc = 0;
    j->status = (uint8_t)status;
    j->state = j->file ? CLEANUP : TERMINAL;
}
static int read_exact(struct ep5_lut_job *j, uint8_t *dst, unsigned count)
{ return j->io.read(j->io.ctx, j->file, dst, count) == (int32_t)count; }
static int row(struct ep5_lut_job *j)
{
    const uint8_t *p = j->scratch;
    int s = slot(u16(p), p[2]);
    unsigned n = u16(p + 6), q = u16(p + 4), bit;
    uint32_t c = u32(p + 8);
    if (s < 0 || (j->slot_seen & (1u << s)) || p[3] != 1 || q > 256 ||
        n < 1 || n > 16 || !label_ok(p + 12)) return 0;
    bit = 1u << (n - 1);
    if ((j->number_seen & bit) && j->look_crc[n - 1] != c) return 0;
    j->slot_seen |= 1u << s; j->number_seen |= bit; j->look_crc[n - 1] = c;
    if (s == j->target) { j->amount = (uint16_t)q; j->number = (uint16_t)n; j->expected_crc = c; }
    return 1;
}
static void clear_job(struct ep5_lut_job *j)
{
    uint8_t *p = (uint8_t *)j;
    for (unsigned i = 0; i < sizeof *j; ++i)
        p[i] = 0;
}
void ep5_lut_job_init(struct ep5_lut_job *j)
{ if (j) { clear_job(j); j->state = TERMINAL; } }
int ep5_lut_job_request(struct ep5_lut_job *j, const struct ep5_look_io *io,
                        struct ep5_look_cache *cache, uint16_t mode,
                        uint8_t variant, uint16_t generation)
{
    int target;
    if (!j || j->status == EP5_LUT_JOB_BUSY || j->file || !generation) return 0;
    clear_job(j);
    j->generation = generation; j->picture_mode = mode; j->variant = variant;
    target = slot(mode, variant);
    if (target < 0) { j->status = EP5_LUT_JOB_STOCK; j->state = TERMINAL; return 1; }
    if (!io || !io->open || !io->read || !io->close || !cache ||
        !cache->active || !cache->staging) {
        j->status = EP5_LUT_JOB_ERROR; j->state = TERMINAL; return 1;
    }
    j->io = *io; j->cache = cache; j->target = (uint8_t)target;
    j->status = EP5_LUT_JOB_BUSY; j->state = OPEN_INDEX;
    return 1;
}
int ep5_lut_job_bind(struct ep5_lut_job *job, uint16_t number, uint32_t crc,
                     uint16_t amount)
{
    if (!job || job->state != OPEN_INDEX || job->status != EP5_LUT_JOB_BUSY ||
        number < 1 || number > 16 || !amount || amount > 256)
        return 0;
    job->bound_number = number;
    job->bound_crc = crc;
    job->bound_amount = amount;
    return 1;
}
int ep5_lut_job_step(struct ep5_lut_job *j, uint16_t current_generation)
{
    uint8_t *table;
    if (!j) return EP5_LUT_JOB_ERROR;
    if (j->status == EP5_LUT_JOB_BUSY && current_generation != j->generation) {
        finish(j, EP5_LUT_JOB_CANCELLED);
        /* Do not close a file in the same call that observes cancellation.
         * The caller's worker budget remains one bounded operation per step. */
        if (j->state == CLEANUP)
            return EP5_LUT_JOB_BUSY;
    }
    if (j->state == CLEANUP) {
        (void)j->io.close(j->io.ctx, j->file); j->file = 0; j->state = TERMINAL;
        return j->status;
    }
    if (j->status != EP5_LUT_JOB_BUSY) return j->status;
    switch (j->state) {
    case OPEN_INDEX:
        j->file = j->io.open(j->io.ctx, "EP5LUT/INDEX.EP5");
        if (!j->file) finish(j, EP5_LUT_JOB_ERROR); else j->state = INDEX_HEADER;
        break;
    case INDEX_HEADER:
        if (!read_exact(j, j->scratch, 20) || !magic(j->scratch, "EP5IDX02") ||
            u16(j->scratch + 8) != 2 || !(j->rows = u16(j->scratch + 10)) ||
            j->rows > 32 || u32(j->scratch + 12) != j->rows * ROW_BYTES) {
            finish(j, EP5_LUT_JOB_ERROR); break;
        }
        j->bytes = u32(j->scratch + 16); j->crc = 0xffffffffu; j->state = INDEX_ROW;
        break;
    case INDEX_ROW:
        if (!read_exact(j, j->scratch, ROW_BYTES) || !row(j)) {
            finish(j, EP5_LUT_JOB_ERROR); break;
        }
        j->crc = crc_step(j->crc, j->scratch, ROW_BYTES);
        if (++j->row_index == j->rows) j->state = INDEX_EOF;
        break;
    case INDEX_EOF:
        if ((j->crc ^ 0xffffffffu) != j->bytes ||
            j->io.read(j->io.ctx, j->file, j->scratch, 1) != 0) {
            finish(j, EP5_LUT_JOB_ERROR); break;
        }
        j->state = CLOSE_INDEX; break;
    case CLOSE_INDEX: {
        int rc = j->io.close(j->io.ctx, j->file); j->file = 0;
        if (rc) finish(j, EP5_LUT_JOB_ERROR);
        else if (j->bound_number) {
            if (j->number != j->bound_number || j->expected_crc != j->bound_crc)
                finish(j, EP5_LUT_JOB_ERROR);
            else {
                j->amount = j->bound_amount;
                j->state = OPEN_TABLE;
            }
        } else if (!j->number || !j->amount) finish(j, EP5_LUT_JOB_STOCK);
        else j->state = OPEN_TABLE;
        break;
    }
    case OPEN_TABLE: {
        char path[] = "EP5LUT/L0000000.LUT";
        path[13] = (char)('0' + (j->number >= 10));
        path[14] = (char)('0' + (j->number % 10));
        j->file = j->io.open(j->io.ctx, path);
        if (!j->file) finish(j, EP5_LUT_JOB_ERROR); else j->state = TABLE_HEADER;
        break;
    }
    case TABLE_HEADER:
        if (!read_exact(j, j->scratch, 24) || !magic(j->scratch, "EP5LUT01") ||
            u16(j->scratch + 8) != 17 || u16(j->scratch + 10) != 1 ||
            u32(j->scratch + 12) != j->number || u32(j->scratch + 16) != TABLE_BYTES ||
            u32(j->scratch + 20) != j->expected_crc) {
            finish(j, EP5_LUT_JOB_ERROR); break;
        }
        j->bytes = 0; j->crc = 0xffffffffu; j->state = TABLE_DATA; break;
    case TABLE_DATA: {
        unsigned n = TABLE_BYTES - j->bytes;
        if (n > EP5_LUT_JOB_CHUNK) n = EP5_LUT_JOB_CHUNK;
        table = (uint8_t *)j->cache->staging + j->bytes;
        if (!read_exact(j, table, n)) { finish(j, EP5_LUT_JOB_ERROR); break; }
        j->crc = crc_step(j->crc, table, n); j->bytes += n;
        if (j->bytes == TABLE_BYTES) j->state = TABLE_EOF;
        break;
    }
    case TABLE_EOF:
        if ((j->crc ^ 0xffffffffu) != j->expected_crc ||
            j->io.read(j->io.ctx, j->file, j->scratch, 1) != 0) {
            finish(j, EP5_LUT_JOB_ERROR); break;
        }
        j->state = CLOSE_TABLE; break;
    case CLOSE_TABLE: {
        int rc = j->io.close(j->io.ctx, j->file); j->file = 0;
        if (rc) finish(j, EP5_LUT_JOB_ERROR);
        else { j->bytes = 0; j->state = CONVERT; }
        break;
    }
    case CONVERT: {
        unsigned n = TABLE_BYTES - j->bytes;
        if (n > EP5_LUT_JOB_CHUNK) n = EP5_LUT_JOB_CHUNK;
        table = (uint8_t *)j->cache->staging;
        for (unsigned i = 0; i < n; i += 2) {
            unsigned pos = j->bytes + i;
            j->cache->staging[pos / 2] = u16(table + pos);
        }
        j->bytes += n;
        if (j->bytes == TABLE_BYTES) j->state = COMMIT;
        break;
    }
    case COMMIT: {
        uint16_t *old = j->cache->active;
        j->cache->active = j->cache->staging; j->cache->staging = old;
        j->result.table = j->cache->active; j->result.amount_q8 = j->amount;
        j->result.number = j->number; j->result.look_crc = j->expected_crc;
        j->status = EP5_LUT_JOB_APPLY; j->state = TERMINAL;
        break;
    }
    default: finish(j, EP5_LUT_JOB_ERROR); break;
    }
    /* Cleanup is a separate step so even error paths perform at most one IO. */
    return j->state == CLEANUP ? EP5_LUT_JOB_BUSY : j->status;
}
int ep5_lut_job_result(const struct ep5_lut_job *j, uint16_t generation,
                       struct ep5_look_selection *out)
{
    if (!out) return EP5_LUT_JOB_ERROR;
    out->table = 0; out->amount_q8 = out->number = 0; out->look_crc = 0;
    if (!j) return EP5_LUT_JOB_ERROR;
    if (j->state == CLEANUP || j->status == EP5_LUT_JOB_BUSY) return EP5_LUT_JOB_BUSY;
    if (generation != j->generation) return EP5_LUT_JOB_CANCELLED;
    if (j->status == EP5_LUT_JOB_APPLY) *out = j->result;
    return j->status;
}
