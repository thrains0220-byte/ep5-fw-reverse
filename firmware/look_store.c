/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "look_store.h"

#define TABLE_BYTES (2u*EP5_LUT_VALUES)
#define ROW_BYTES 28u

static uint16_t u16(const uint8_t *p)
{ return (uint16_t)(p[0] | ((uint16_t)p[1] << 8)); }
static uint32_t u32(const uint8_t *p)
{ return u16(p) | ((uint32_t)u16(p+2) << 16); }
static int magic(const uint8_t *p, const char *s)
{ for (unsigned i=0; i<8; ++i) if (p[i]!=(uint8_t)s[i]) return 0; return 1; }
__attribute__((noinline)) static uint32_t crc_step(uint32_t c, const uint8_t *p, uint32_t n)
{
    while (n--) {
        c ^= *p++;
        for (unsigned i=0; i<8; ++i) c=(c>>1) ^ ((0u-(c&1u)) & 0xedb88320u);
    }
    return c;
}
static int slot(uint16_t m, uint8_t v)
{
    if (v==1 && m>=100 && m<=109) return (int)m-100;
    if (m==105 && (v==2 || v==3)) return 8+v;
    if (v==1 && (m==119 || m==120)) return (int)m-107;
    return -1;
}
/* Short name is metadata and is never forwarded as an address, format string,
 * path or menu string. Enforce wire structure; desktop owns text normalization. */
static int label_ok(const uint8_t *p)
{
    unsigned n=0; uint16_t last=0;
    while (n<8) {
        uint16_t c=u16(p+2*n);
        if (!c) break;
        if (n>=6 || c<32 || (c>=127 && c<=159) || (c>=0xd800 && c<=0xdfff) ||
            c==0xfffe || c==0xffff || (!n && c==32)) return 0;
        last=c; ++n;
    }
    if (!n || last==32) return 0;
    for (; n<8; ++n) if (u16(p+2*n)) return 0;
    return 1;
}
static int exact(const struct ep5_look_io *io, void *f, uint8_t *p, uint32_t n)
{ return io->read(io->ctx,f,p,n)==(int32_t)n; }
static int eof(const struct ep5_look_io *io, void *f)
{ uint8_t x; return io->read(io->ctx,f,&x,1)==0; }

struct wanted { uint16_t amount, number; uint32_t crc; };
static int index_rows(const struct ep5_look_io *io, void *f, int target, struct wanted *w)
{
    uint8_t h[20], r[ROW_BYTES];
    uint32_t slot_seen=0, number_seen=0, look_crc[16], crc=0xffffffffu;
    if (!exact(io,f,h,sizeof h) || !magic(h,"EP5IDX02") || u16(h+8)!=2) return 0;
    unsigned count=u16(h+10);
    if (!count || count>32 || u32(h+12)!=count*ROW_BYTES) return 0;
    for (unsigned i=0; i<count; ++i) {
        if (!exact(io,f,r,sizeof r)) return 0;
        crc=crc_step(crc,r,sizeof r);
        int s=slot(u16(r),r[2]); unsigned n=u16(r+6), q=u16(r+4);
        uint32_t expected=u32(r+8);
        if (s<0 || (slot_seen&(1u<<s)) || r[3]!=1 || q>256 || n<1 || n>16 || !label_ok(r+12)) return 0;
        slot_seen|=1u<<s;
        unsigned bit=1u<<(n-1);
        if ((number_seen&bit) && look_crc[n-1]!=expected) return 0;
        number_seen|=bit; look_crc[n-1]=expected;
        if (s==target) { w->amount=(uint16_t)q; w->number=(uint16_t)n; w->crc=expected; }
    }
    return (crc^0xffffffffu)==u32(h+16) && eof(io,f);
}
static int table_read(const struct ep5_look_io *io, void *f, const struct wanted *w, uint16_t *stage)
{
    uint8_t h[24], *bytes=(uint8_t *)stage; uint32_t crc=0xffffffffu;
    if (!exact(io,f,h,sizeof h) || !magic(h,"EP5LUT01") || u16(h+8)!=17 || u16(h+10)!=1 ||
        u32(h+12)!=w->number || u32(h+16)!=TABLE_BYTES || u32(h+20)!=w->crc) return 0;
    for (unsigned i=0; i<TABLE_BYTES;) {
        unsigned n=TABLE_BYTES-i; if (n>2048) n=2048;
        if (!exact(io,f,bytes+i,n)) return 0;
        crc=crc_step(crc,bytes+i,n); i+=n;
    }
    if ((crc^0xffffffffu)!=w->crc || !eof(io,f)) return 0;
    /* Wire bytes are little endian; expose native uint16_t in original red-fastest order. */
    for (unsigned i=0; i<EP5_LUT_VALUES; ++i) stage[i]=u16(bytes+2*i);
    return 1;
}
int ep5_look_cache_init(struct ep5_look_cache *cache, void *a, size_t an, void *b, size_t bn)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if (!cache) return EP5_LOOK_BAD;
    cache->active=cache->staging=NULL;
    if (!a || !b || an<TABLE_BYTES || bn<TABLE_BYTES || ((x|y)&1u) ||
        x>UINTPTR_MAX-(TABLE_BYTES-1) || y>UINTPTR_MAX-(TABLE_BYTES-1) ||
        (x>=y?x-y:y-x)<TABLE_BYTES) return EP5_LOOK_BAD;
    cache->active=a; cache->staging=b;
    return EP5_LOOK_STOCK;
}
int ep5_look_load(const struct ep5_look_io *io, struct ep5_look_cache *cache, uint16_t m,
                  uint8_t v, struct ep5_look_selection *selection)
{
    if (!selection) return EP5_LOOK_BAD;
    selection->table=NULL; selection->amount_q8=selection->number=0;
    int target=slot(m,v);
    if (target<0) return EP5_LOOK_STOCK;
    if (!io || !io->open || !io->read || !io->close || !cache || !cache->active || !cache->staging)
        return EP5_LOOK_BAD;
    void *f=io->open(io->ctx,"EP5LUT/INDEX.EP5");
    if (!f) return EP5_LOOK_BAD;
    struct wanted w={0,0,0};
    int ok=index_rows(io,f,target,&w);
    if (io->close(io->ctx,f)!=0 || !ok) return EP5_LOOK_BAD;
    if (!w.number || !w.amount) return EP5_LOOK_STOCK;
    char path[]="EP5LUT/L0000000.LUT";
    path[13]=(char)('0'+(w.number>=10)); path[14]=(char)('0'+(w.number%10));
    f=io->open(io->ctx,path);
    if (!f) return EP5_LOOK_BAD;
    ok=table_read(io,f,&w,cache->staging);
    if (io->close(io->ctx,f)!=0 || !ok) return EP5_LOOK_BAD;
    uint16_t *old=cache->active;
    cache->active=cache->staging; cache->staging=old;
    selection->table=cache->active; selection->number=w.number; selection->amount_q8=w.amount;
    return EP5_LOOK_APPLY;
}
