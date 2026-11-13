/* SPDX-License-Identifier: GPL-3.0-or-later
 * Execute stock E-P5 file-call instructions, without a filesystem or device. */
#include "emu.h"

#define BASE 0x7e101020u
#define BYTES 15728576u
#define STACK 0x10000000u
#define HANDLE 0x125af004u /* synthetic, never dereferenced */
#define END 0x7e3d2fe8u
#define SELECTOR_END 0x7e3fcc78u
#define DEST 0xbb0c22c0u /* original debug routine's destination, deliberately unmapped */
static uint8_t *image, ram[65536];
static int direct, scenario, stopped, opened, read_calls, closed;
static uint32_t read_count;
uint64_t emu_ns;

/* The normal file wrappers execute from the E-P5 image. Only their backend,
 * task selector and diagnostic prints are substitutes. */
static const struct hook { uint32_t pc; uint8_t ret[8]; } hooks[] = {
    {0x7e3d299a, {0xdf,0,4}}, {0x7e3d29a4, {0xdf,0,4}}, /* debug prints */
    {0x7e2914f1, {0xdf,0,8}}, /* choose backend: local task or routed message */
    {0x7e2960db, {0xdf,0xf0,64}}, {0x7e296da5, {0xdf,0xf0,20}},
    {0x7e29640e, {0xdf,0xb0,16}}, {0x7e13452b, {0xdf,0xc0,12}},
    {0x7e3fd443, {0xdf,0,4}}, {0x7e3fd94a, {0xdf,0,0}}, {0x7e3fd922, {0xdf,0x80,4}},
};
static int within(uint32_t a, uint32_t n, uint32_t b, uint32_t bytes)
{ return a >= b && (uint64_t)a+n <= (uint64_t)b+bytes; }

uint8_t *mem_host(uint32_t a, uint32_t n)
{
    for (size_t i=0; i<sizeof hooks/sizeof *hooks; ++i)
        if (within(a,n,hooks[i].pc,8)) return (uint8_t *)hooks[i].ret+(a-hooks[i].pc);
    if (within(a,n,BASE,BYTES)) return image+(a-BASE);
    if (within(a,n,STACK,sizeof ram)) return ram+(a-STACK);
    return NULL;
}
uint32_t mem_rd(uint32_t a, int n)
{
    uint8_t *p=mem_host(a,n); uint32_t v=0;
    if (!p) emu_abort(PC,"unmapped read %08x",a);
    for (int i=0;i<n;i++) v|=(uint32_t)p[i]<<(8*i);
    return v;
}
void mem_wr(uint32_t a,uint32_t v,int n)
{
    if (!within(a,n,STACK,sizeof ram)) emu_abort(PC,"write outside stack %08x",a);
    for (int i=0;i<n;i++) ram[a-STACK+i]=(uint8_t)(v>>(8*i));
}
void mem_misaligned(uint32_t a,int n,int wr) { emu_abort(PC,"misaligned %08x/%d/%d",a,n,wr); }
void soc_tick(uint64_t cycles) { emu_ns+=cycles; }
uint64_t soc_next_event(void) { return emu_ns+1; }
int hle_is_hook(uint32_t pc)
{
    if (pc==END || pc==SELECTOR_END) return 1;
    for (size_t i=0;i<sizeof hooks/sizeof *hooks;i++) if (pc==hooks[i].pc) return 1;
    return 0;
}
static void expect(int ok) { if (!ok) emu_abort(PC,"file service ABI/sequence mismatch"); }
static void open_args(uint32_t p,uint32_t m)
{
    expect(!opened && !read_calls && !closed && p==0x7e507b59 && m==0x7e507b69);
    expect(!memcmp(mem_host(p,16),"C:\\TEST0000.RAW",16) && mem_rd(m,2)=='r');
    opened++;
}
static void read_args(uint32_t d,uint32_t s,uint32_t n,uint32_t h)
{
    expect(opened==1 && !read_calls && !closed && d==DEST && s==1 && n==307200 && h==HANDLE);
    read_count=n; read_calls++;
}
static void close_args(uint32_t h) { expect(opened==1 && read_calls==1 && !closed && h==HANDLE); closed++; }
int hle_check(cpu_t *c)
{
    uint32_t *r=c->regs, pc=r[REG_PC], a=r[REG_A0], b=r[REG_A0+1];
    if (pc==END || pc==SELECTOR_END) { stopped=emu_stop=1; return 1; }
    if (pc==0x7e2914f1) r[0]=direct;
    if (pc==0x7e2960db) { expect(direct); open_args(a,b); r[REG_A0]=scenario==1?0:HANDLE; }
    if (pc==0x7e296da5) { expect(direct); read_args(a,r[0],r[1],b); r[0]=scenario==2?7:307200; }
    if (pc==0x7e29640e) { expect(direct); close_args(a); r[0]=0; }
    if (pc==0x7e13452b) {
        expect(!direct && r[0]==0x22);
        switch(r[1]) {
        case 0x10001: open_args(mem_rd(a+4,4),mem_rd(a+8,4)); mem_wr(a,scenario==1?0:HANDLE,4); break;
        case 0x10005: read_args(mem_rd(a+4,4),mem_rd(a+8,4),mem_rd(a+12,4),mem_rd(a+16,4));
            mem_wr(a,scenario==2?7:307200,4); break;
        case 0x10002: close_args(mem_rd(a+4,4)); mem_wr(a,0,4); break;
        default: emu_abort(pc,"unexpected file service message %x",r[1]);
        }
        r[0]=0;
    }
    return 0; /* execute the modeled target's actual frame-return instruction */
}
int main(int argc,char **argv)
{
    if (argc!=4 && argc!=5) return 2;
    direct=atoi(argv[2]); scenario=atoi(argv[3]);
    FILE *f=fopen(argv[1],"rb"); image=malloc(BYTES);
    if (!f || !image || fread(image,1,BYTES,f)!=BYTES || fgetc(f)!=EOF) return 2;
    fclose(f);
    if (argc==5 && !strcmp(argv[4],"selector")) {
        cpus[0].regs[REG_PC]=0x7e3fcb10; cpus[0].regs[REG_SP]=STACK+0xf000;
        cpus[0].regs[0]=direct; cpus[0].regs[1]=scenario;
        cpus[0].running=1; cpus[0].irq_level=7;
        cpu_run(5000,0);
        printf("%u\n",cpus[0].regs[0]);
        free(image); return stopped && cpus[0].regs[REG_SP]==STACK+0xf000 ? 0:1;
    }
    cpus[0].regs[REG_PC]=0x7e3d2f90; /* body through final RET, excluding prologue/epilogue */
    cpus[0].regs[REG_SP]=STACK+0xf000; cpus[0].running=1; cpus[0].irq_level=7;
    cpu_run(5000,0);
    int result=(int32_t)cpus[0].regs[0];
    int ok=stopped && cpus[0].regs[REG_SP]==STACK+0xf000 && opened==1 &&
        read_calls==(scenario!=1) && closed==read_calls && result==(scenario==1?-1:0);
    printf("{\"direct\":%d,\"case\":%d,\"open\":%d,\"read\":%d,\"close\":%d,"
           "\"requested_bytes\":%u,\"caller_result\":%d,\"instructions\":%llu}\n",
           direct,scenario,opened,read_calls,closed,read_count,result,(unsigned long long)cpus[0].icount);
    free(image); return ok?0:1;
}
