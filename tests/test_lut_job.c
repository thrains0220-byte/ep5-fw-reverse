#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "lut_job.h"
#include "lut_preload.h"

#define N EP5_LUT_VALUES
#define TABLE_BYTES (2u*N)
static uint8_t index_data[48], table_data[24 + TABLE_BYTES];
static uint16_t a[N], b[N];
static unsigned pos, max_read;
static int have_table, close_count, fail_close, trailing_index, trailing_table, short_read;
static int locked;
static void (*on_read)(void);
static uint32_t crc32(const uint8_t *p, unsigned n)
{ uint32_t c=0xffffffffu; while(n--){ c^=*p++; for(unsigned i=0;i<8;i++) c=(c>>1)^((0u-(c&1u))&0xedb88320u);} return c^0xffffffffu; }
static void put16(uint8_t *p,uint16_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static void make_files(void)
{
    memset(index_data,0,sizeof index_data); memset(table_data,0,sizeof table_data);
    memcpy(index_data,"EP5IDX02",8); put16(index_data+8,2); put16(index_data+10,1);
    put32(index_data+12,28); put16(index_data+20,105); index_data[22]=2; index_data[23]=1;
    put16(index_data+24,200); put16(index_data+26,2);
    memcpy(index_data+32, "Test", 4);
    for(unsigned i=0;i<N;i++) put16(table_data+24+2*i,(uint16_t)(i*13u));
    memcpy(table_data,"EP5LUT01",8); put16(table_data+8,17); put16(table_data+10,1);
    put32(table_data+12,2); put32(table_data+16,TABLE_BYTES);
    put32(table_data+20,crc32(table_data+24,TABLE_BYTES));
    put32(index_data+28,crc32(table_data+24,TABLE_BYTES));
    put32(index_data+16,crc32(index_data+20,28));
}
static void *open_file(void *ctx,const char *path)
{ (void)ctx; assert(!locked); pos=0; if(!strcmp(path,"EP5LUT/INDEX.EP5")) return (void*)1; if(have_table && !strcmp(path,"EP5LUT/L0000002.LUT")) return (void*)2; return 0; }
static int32_t read_file(void *ctx,void *file,uint8_t *dst,uint32_t n)
{
    const uint8_t *src; unsigned size; (void)ctx; src=(file==(void*)1)?index_data:table_data; size=(file==(void*)1)?sizeof index_data:sizeof table_data;
    assert(!locked);
    if (on_read) on_read();
    if (pos >= size) {
        if ((file == (void *)1 && trailing_index) || (file == (void *)2 && trailing_table)) {
            dst[0] = 0x55;
            return 1;
        }
        return 0;
    }
    if (n > size - pos)
        n = size - pos;
    if (short_read && file == (void *)2 && pos >= 24 && n > 1)
        --n;
    if (n > max_read)
        max_read = n;
    memcpy(dst, src + pos, n);
    pos += n;
    return (int32_t)n;
}
static int close_file(void *ctx,void *file)
{ (void)ctx; (void)file; assert(!locked); ++close_count; return fail_close ? -1 : 0; }
static void run(struct ep5_lut_job *j,uint16_t gen)
{ unsigned guard=1000; int r; do {r=ep5_lut_job_step(j,gen); assert(--guard); } while(r==EP5_LUT_JOB_BUSY); assert(r==EP5_LUT_JOB_APPLY); }
static int until_done(struct ep5_lut_job *j, uint16_t gen)
{ unsigned guard=1000; int r; do { r=ep5_lut_job_step(j,gen); assert(--guard); } while(r==EP5_LUT_JOB_BUSY); return r; }

static struct ep5_lut_preload preload;
static uint32_t mounted_medium;

static void *open_mounted(void *context, uint32_t medium, const char *path)
{
    assert(!locked);
    return medium == mounted_medium ? open_file(context, path) : NULL;
}

static void mount(uint32_t medium)
{
    mounted_medium = medium;
    ep5_lut_preload_media(&preload, medium);
}

static void lock(void *context)
{
    assert(context == &locked && !locked);
    locked = 1;
}

static void unlock(void *context)
{
    assert(context == &locked && locked);
    locked = 0;
}

static int preload_until_done(void)
{
    unsigned remaining = 200;
    int status;
    do {
        assert(remaining--);
        status = ep5_lut_preload_step(&preload);
    } while (status == EP5_LUT_JOB_BUSY);
    return status;
}

static void unmount_during_read(void)
{
    struct ep5_look_selection selection;
    on_read = NULL;
    mount(0);
    assert(ep5_lut_preload_step(&preload) == EP5_LUT_JOB_BUSY);
    assert(!ep5_lut_preload_acquire(&preload, 3, 4, NULL, &selection));
}

static void test_preloading(void)
{
    const struct ep5_lut_preload_io io = {NULL, open_mounted, read_file, close_file};
    const struct ep5_lut_preload_sync sync = {&locked, lock, unlock};
    struct ep5_lut_menu_capture choice = {.picture_mode=105, .variant=2, .number=2, .amount_q8=128};
    struct ep5_look_selection first, second;
    int closed;
    make_files();
    have_table = 1;
    fail_close = trailing_index = trailing_table = short_read = 0;
    put16(index_data + 24, 0);
    put32(index_data + 16, crc32(index_data + 20, 28));
    choice.look_crc = crc32(table_data + 24, TABLE_BYTES);
    assert(!ep5_lut_preload_init(&preload, &io, &sync, a, a, sizeof a));
    assert(ep5_lut_preload_init(&preload, &io, &sync, a, b, sizeof a));
    mount(1);
    assert(ep5_lut_preload_status(&preload, 1, &choice) == EP5_LUT_JOB_IDLE);
    assert(ep5_lut_preload_select(&preload, 1, &choice));
    assert(ep5_lut_preload_status(&preload, 1, &choice) == EP5_LUT_JOB_BUSY);
    closed = close_count;
    assert(!ep5_lut_preload_acquire(&preload, 1, 1, &choice, &first) && !first.table);
    assert(close_count == closed);
    assert(preload_until_done() == EP5_LUT_JOB_APPLY);
    assert(ep5_lut_preload_status(&preload, 1, &choice) == EP5_LUT_JOB_APPLY);
    assert(close_count == closed + 2);
    assert(ep5_lut_preload_acquire(&preload, 1, 1, &choice, &first));
    assert(first.amount_q8 == 128 && first.table[1] == 13);
    choice.amount_q8 = 64;
    assert(ep5_lut_preload_select(&preload, 1, &choice));
    assert(ep5_lut_preload_step(&preload) == EP5_LUT_JOB_APPLY && close_count == closed + 2);
    assert(first.amount_q8 == 128);

    mount(2);
    assert(ep5_lut_preload_status(&preload, 1, &choice) == EP5_LUT_JOB_IDLE);
    assert(ep5_lut_preload_status(&preload, 2, &choice) == EP5_LUT_JOB_IDLE);
    assert(!ep5_lut_preload_select(&preload, 1, &choice));
    assert(!ep5_lut_preload_acquire(&preload, 2, 2, &choice, &second));
    put16(table_data + 26, 4321);
    choice.look_crc = crc32(table_data + 24, TABLE_BYTES);
    put32(table_data + 20, choice.look_crc);
    put32(index_data + 28, choice.look_crc);
    put32(index_data + 16, crc32(index_data + 20, 28));
    assert(ep5_lut_preload_select(&preload, 2, &choice));
    assert(preload_until_done() == EP5_LUT_JOB_APPLY);
    assert(first.table[1] == 13 && !ep5_lut_preload_release(&preload, 9));
    assert(!ep5_lut_preload_acquire(&preload, 2, 2, &choice, &second));

    mount(3);
    assert(ep5_lut_preload_select(&preload, 3, &choice));
    closed = close_count;
    assert(ep5_lut_preload_step(&preload) == EP5_LUT_PRELOAD_WAIT_SHOT && close_count == closed);
    assert(first.table[1] == 13 && ep5_lut_preload_release(&preload, 1));
    assert(ep5_lut_preload_step(&preload) == EP5_LUT_JOB_BUSY);
    on_read = unmount_during_read;
    assert(ep5_lut_preload_step(&preload) == EP5_LUT_JOB_BUSY && !on_read);
    assert(preload_until_done() == EP5_LUT_JOB_STOCK && close_count == closed + 1);
    assert(!ep5_lut_preload_release(&preload, 1));

    mount(4);
    choice.look_crc ^= 1;
    assert(ep5_lut_preload_select(&preload, 4, &choice));
    closed = close_count;
    assert(preload_until_done() == EP5_LUT_JOB_ERROR && close_count == closed + 1);
    assert(ep5_lut_preload_status(&preload, 4, &choice) == EP5_LUT_JOB_ERROR);
    assert(!ep5_lut_preload_acquire(&preload, 4, 2, &choice, &second));
    choice.look_crc ^= 1;
    assert(ep5_lut_preload_select(&preload, 4, &choice));
    assert(preload_until_done() == EP5_LUT_JOB_APPLY);
    struct ep5_lut_menu_capture stale = choice;
    stale.variant = 1;
    assert(!ep5_lut_preload_acquire(&preload, 4, 2, &stale, &second));
    stale = choice;
    stale.amount_q8 = 128;
    assert(!ep5_lut_preload_acquire(&preload, 4, 2, &stale, &second));
    assert(ep5_lut_preload_acquire(&preload, 4, 2, &choice, &second));
    assert(second.table[1] == 4321 && second.amount_q8 == 64);
    assert(!ep5_lut_preload_release(&preload, 1));
    assert(ep5_lut_preload_release(&preload, 2));
    choice.amount_q8 = 0;
    assert(ep5_lut_preload_select(&preload, 4, &choice));
    assert(ep5_lut_preload_status(&preload, 4, &choice) == EP5_LUT_JOB_STOCK);
    assert(!ep5_lut_preload_acquire(&preload, 4, 3, &choice, &second));

    /* The mount changes before the controller receives the notification. */
    choice.amount_q8 = 64;
    assert(ep5_lut_preload_status(&preload, 4, &choice) == EP5_LUT_JOB_IDLE);
    assert(ep5_lut_preload_select(&preload, 4, &choice));
    mounted_medium = 5;
    closed = close_count;
    assert(preload_until_done() == EP5_LUT_JOB_ERROR && close_count == closed);
    assert(!ep5_lut_preload_acquire(&preload, 4, 4, &choice, &second));
}
int main(void)
{
    struct ep5_look_io io={0,open_file,read_file,close_file}; struct ep5_look_cache cache;
    struct ep5_lut_job job; struct ep5_look_selection out; make_files();
    assert(ep5_look_cache_init(&cache,a,sizeof a,b,sizeof b)==0); have_table=1; max_read=0;
    ep5_lut_job_init(&job); assert(ep5_lut_job_request(&job,&io,&cache,105,2,7)); run(&job,7);
    assert(ep5_lut_job_result(&job,7,&out)==EP5_LUT_JOB_APPLY); assert(out.amount_q8==200 && out.number==2 && out.table==cache.active);
    assert(out.look_crc == crc32(table_data + 24, TABLE_BYTES));
    assert(max_read<=EP5_LUT_JOB_CHUNK); assert(out.table[0]==0 && out.table[1]==13);
    ep5_lut_job_init(&job); assert(ep5_lut_job_request(&job,&io,&cache,105,2,8));
    assert(ep5_lut_job_step(&job,8)==EP5_LUT_JOB_BUSY); assert(ep5_lut_job_step(&job,9)==EP5_LUT_JOB_BUSY);
    assert(ep5_lut_job_step(&job,9)==EP5_LUT_JOB_CANCELLED); assert(ep5_lut_job_result(&job,9,&out)==EP5_LUT_JOB_CANCELLED);
    have_table=0; ep5_lut_job_init(&job); assert(ep5_lut_job_request(&job,&io,&cache,105,2,10));
    { unsigned guard=1000; int r; do {r=ep5_lut_job_step(&job,10); assert(--guard);} while(r==EP5_LUT_JOB_BUSY); assert(r==EP5_LUT_JOB_ERROR); }
    ep5_lut_job_init(&job); assert(ep5_lut_job_request(&job,&io,&cache,1,1,11)); assert(ep5_lut_job_result(&job,11,&out)==EP5_LUT_JOB_STOCK);
    have_table=1;
    {
        uint16_t *active = cache.active;
        for (unsigned fault = 0; fault < 6; ++fault) {
            make_files(); fail_close = trailing_index = trailing_table = short_read = 0;
            if (fault == 0) index_data[16] ^= 1;
            if (fault == 1) table_data[30] ^= 1;
            if (fault == 2) trailing_index = 1;
            if (fault == 3) trailing_table = 1;
            if (fault == 4) short_read = 1;
            if (fault == 5) fail_close = 1;
            int before = close_count;
            ep5_lut_job_init(&job);
            assert(ep5_lut_job_request(&job,&io,&cache,105,2,(uint16_t)(20+fault)));
            assert(until_done(&job,(uint16_t)(20+fault)) == EP5_LUT_JOB_ERROR);
            assert(close_count > before && cache.active == active);
            assert(ep5_lut_job_result(&job,(uint16_t)(20+fault),&out) == EP5_LUT_JOB_ERROR);
            assert(out.table == 0 && out.amount_q8 == 0 && out.number == 0);
        }
    }
    test_preloading();
    return 0;
}
