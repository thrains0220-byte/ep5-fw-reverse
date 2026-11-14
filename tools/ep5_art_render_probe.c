/* Run the original ART page assembly with explicitly modeled services. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "emu.h"

#define BASE 0x7e101020u
#define SIZE 15728576u
#define RAM 0x10000000u
#define RAM_SIZE 65536u
#define CALLER (RAM + 0x100u)
#define OBJ (RAM + 0x1000u)
#define AVAILABLE (RAM + 0x2000u)
#define SERVICE (RAM + 0x3000u)
#define VTABLE (RAM + 0x3100u)
#define METHOD (RAM + 0x3200u)
#define FRAME (RAM + 0xf000u)
#define DRAW 0x7eb28d11u
#define INIT 0x7ea13b47u
#define UPDATE 0x7ea13b5fu
#define SETTING 0x7eb4a177u
#define GET_SERVICE 0x7e66bba5u
#define DESC 0x7edf7bdcu
#define RECORDS 0x7edf7908u

static uint8_t *image, ram[RAM_SIZE];
static uint8_t init_ret[8] = {0xdf,0,4}, update_ret[8] = {0xdf,0xa0,16};
static uint8_t setting_ret[8] = {0xdf,0xa0,12}, service_ret[8] = {0xdf,0,4};
static unsigned init_calls, updates, settings, invalid_write, stopped, monitoring;
static uint32_t selected_snapshot[3][4];
uint64_t emu_ns;

uint8_t *mem_host(uint32_t a, uint32_t n)
{
    if (a >= INIT && (uint64_t)a+n <= INIT+8) return init_ret+a-INIT;
    if (a >= UPDATE && (uint64_t)a+n <= UPDATE+8) return update_ret+a-UPDATE;
    if (a >= SETTING && (uint64_t)a+n <= SETTING+8) return setting_ret+a-SETTING;
    if (a >= GET_SERVICE && (uint64_t)a+n <= GET_SERVICE+8) return service_ret+a-GET_SERVICE;
    if (a >= BASE && (uint64_t)a+n <= (uint64_t)BASE+SIZE) return image+a-BASE;
    if (a >= RAM && (uint64_t)a+n <= (uint64_t)RAM+RAM_SIZE) return ram+a-RAM;
    return NULL;
}
uint32_t mem_rd(uint32_t a, int n)
{
    uint8_t *p=mem_host(a,n); uint32_t v=0;
    if (!p) emu_abort(PC,"unmapped read %08x",a);
    for(int i=0;i<n;i++) v|=(uint32_t)p[i]<<(8*i);
    return v;
}
void mem_wr(uint32_t a,uint32_t v,int n)
{
    if (a<RAM || (uint64_t)a+n>(uint64_t)RAM+RAM_SIZE) emu_abort(PC,"unmapped write %08x",a);
    if (monitoring && !(a>=OBJ+200 && (uint64_t)a+n<=OBJ+412) &&
        !(a>=FRAME-2048 && (uint64_t)a+n<=FRAME+32)) {
        ++invalid_write;
        if (getenv("EP5_TRACE")) fprintf(stderr,"unexpected write pc=%08x addr=%08x n=%d\n",PC,a,n);
    }
    uint8_t *p=mem_host(a,n); for(int i=0;i<n;i++) p[i]=(uint8_t)(v>>(8*i));
}
void mem_misaligned(uint32_t a,int n,int w) { emu_abort(PC,"misaligned %08x/%d/%d",a,n,w); }
int hle_is_hook(uint32_t a)
{ return a==INIT || a==UPDATE || a==SETTING || a==GET_SERVICE || a==METHOD || a==CALLER+7; }
int hle_check(cpu_t *c)
{
    uint32_t pc=c->regs[REG_PC], sp=c->regs[REG_SP], a=c->regs[REG_A0];
    if(pc==CALLER+7) { stopped=emu_stop=1; return 1; }
    if(pc==INIT) { ++init_calls; mem_wr(sp+4,c->regs[REG_MDR],4); c->regs[REG_D0]=0; }
    if(pc==SETTING) { ++settings; mem_wr(sp+12,c->regs[REG_MDR],4); mem_wr(a,0,4); c->regs[REG_D0]=0; }
    if(pc==GET_SERVICE) { mem_wr(sp+4,c->regs[REG_MDR],4); c->regs[REG_A0]=SERVICE; }
    if(pc==METHOD) c->regs[REG_D0]=0;
    if(pc==UPDATE) {
        if(updates<3) {
            selected_snapshot[updates][0]=c->regs[REG_D0];
            selected_snapshot[updates][1]=c->regs[REG_D0+1];
            selected_snapshot[updates][2]=a;
            selected_snapshot[updates][3]=c->regs[REG_A0+1];
        }
        ++updates; mem_wr(sp+16,c->regs[REG_MDR],4); c->regs[REG_D0]=0;
    }
    return 0;
}
void soc_tick(uint64_t cycles) { emu_ns+=cycles; }
uint64_t soc_next_event(void) { return emu_ns+1; }

static int run(unsigned selection, uint16_t mask)
{
    memset(cpus,0,sizeof cpus[0]); memset(ram,0,sizeof ram); monitoring=0;
    mem_wr(CALLER,0xdd,1); mem_wr(CALLER+1,DRAW-CALLER,4);
    mem_wr(CALLER+5,0xf0,1); mem_wr(CALLER+6,84,1);
    mem_wr(OBJ+412,DESC,4); mem_wr(OBJ+416,selection,2); mem_wr(OBJ+420,AVAILABLE,4);
    for(unsigned i=0;i<13;i++) mem_wr(AVAILABLE+i,(mask>>i)&1,1);
    mem_wr(SERVICE,VTABLE,4); mem_wr(VTABLE+20,METHOD,4);
    mem_wr(METHOD,0xf0,1); mem_wr(METHOD+1,0xfc,1); /* rets */
    cpu_t *c=&cpus[0]; c->running=1; c->irq_level=7; c->regs[REG_PC]=CALLER;
    c->regs[REG_SP]=FRAME; c->regs[REG_A0]=OBJ;
    c->regs[REG_D0+2]=0x12345678; c->regs[REG_D0+3]=0x87654321;
    c->regs[REG_A0+2]=0x13572468; c->regs[REG_A0+3]=0x24681357;
    init_calls=updates=settings=invalid_write=stopped=emu_stop=0; monitoring=1;
    cpu_run(200000,0);
    if (!stopped || invalid_write || c->regs[REG_SP]!=FRAME || init_calls!=3 || updates!=3 ||
        c->regs[REG_D0+2]!=0x12345678 || c->regs[REG_D0+3]!=0x87654321 ||
        c->regs[REG_A0+2]!=0x13572468 || c->regs[REG_A0+3]!=0x24681357) {
        fprintf(stderr,"selection=%u pc=%08x sp=%08x stop=%u init=%u update=%u settings=%u invalid=%u\n",
                selection,c->regs[REG_PC],c->regs[REG_SP],stopped,init_calls,updates,settings,invalid_write);
        return 0;
    }
    unsigned rank=0;
    for(unsigned i=0;i<selection;i++) rank+=(mask>>i)&1;
    if (selected_snapshot[0][0]!=58 || selected_snapshot[0][1]!=188 || selected_snapshot[0][2]!=OBJ+200 || selected_snapshot[0][3]!=1 ||
        selected_snapshot[1][0]!=0 || selected_snapshot[1][1]!=12 || selected_snapshot[1][2]!=OBJ+388 || selected_snapshot[1][3]!=1 ||
        selected_snapshot[2][0]!=15 || selected_snapshot[2][1]!=12 || selected_snapshot[2][2]!=OBJ+400 || selected_snapshot[2][3]!=1 ||
        mem_rd(OBJ+200,2)!=selection+1 || mem_rd(OBJ+202,2)!=mem_rd(RECORDS+selection*44+4,2) ||
        mem_rd(OBJ+214,2)!=rank/4) return 0;
    unsigned row=0, visible=0;
    for(unsigned i=0;i<13;i++) {
        if (!((mask>>i)&1)) continue;
        if (row/4==rank/4) {
            unsigned highlighted=(i==selection);
            unsigned expected=mem_rd(RECORDS+i*44+(highlighted?8:6),2);
            if(mem_rd(OBJ+216+visible*4,2)!=expected ||
               mem_rd(OBJ+218+visible*4,1)!=(highlighted?2:1)) {
                fprintf(stderr,"selection=%u row=%u visible=%u id=%u expected=%u flag=%u\n",
                        selection,i,visible,mem_rd(OBJ+216+visible*4,2),expected,mem_rd(OBJ+218+visible*4,1));
                return 0;
            }
            ++visible;
        }
        ++row;
    }
    if (getenv("EP5_TRACE")) {
        fprintf(stderr,"selection=%u page:",selection);
        for(unsigned i=0;i<32;i++) fprintf(stderr," %02x",mem_rd(OBJ+200+i,1));
        fprintf(stderr,"\n");
    }
    return 1;
}
int main(int argc,char **argv)
{
    if(argc!=2) return 2;
    FILE *f=fopen(argv[1],"rb"); image=malloc(SIZE);
    if(!f || !image || fread(image,1,SIZE,f)!=SIZE || fgetc(f)!=EOF) return 2;
    fclose(f);
    for(unsigned i=0;i<13;i++) if(!run(i,0x1fff)) { fprintf(stderr,"case %u failed\n",i); return 1; }
    for(unsigned i=0;i<13;i++) if((0x1293u>>i)&1) if(!run(i,0x1293)) { fprintf(stderr,"sparse case %u failed\n",i); return 1; }
    puts("{\"cases\":19,\"stock_page_assembly_executed\":true,\"resource_rows_and_paging_verified\":true,\"modeled_services\":true,\"updates_per_case\":3,\"stack_and_callee_saved_preserved\":true}");
    free(image); return 0;
}
