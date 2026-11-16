/* Execute stock ART assembly and GUI copies; OS locks/notification stay modeled. */
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
#define TABLE 0x602be350u
#define TABLE_ROM 0x7e5a3810u
#define MANAGER_GLOBAL 0x602b75b4u
#define SYNC_GLOBALS 0x602b6e2cu
#define MANAGER (RAM + 0x4000u)
#define OBSERVER (RAM + 0x4100u)
#define NODE (RAM + 0x4200u)
#define FLAGS (RAM + 0x4300u)
#define SOURCE (RAM + 0x5000u)
#define LOCK (RAM + 0x3300u)
#define UNLOCK (RAM + 0x3310u)
#define COPY 0x7e10646fu
#define MARK 0x7ea142e7u
#define NOTIFY 0x7ea1431cu

static uint8_t *image, ram[RAM_SIZE];
static uint8_t setting_ret[8] = {0xdf,0xa0,12}, service_ret[8] = {0xdf,0,4};
static uint8_t notify_ret[8] = {0xdf,0x20,64};
static uint8_t manager_global[4], sync_globals[8], payloads[3][220];
static const uint32_t slot_ids[3] = {0,15,58};
static const uint32_t slot_buffers[3] = {0x606eb274u,0x606eb452u,0x606f1670u};
static const unsigned slot_sizes[3] = {12,12,188};
static unsigned init_calls, updates, settings, invalid_write, stopped, monitoring;
static unsigned locked, lock_fail, copies, marks, notifications, order_size;
static unsigned reading;
static uint32_t last_id, last_source, last_size;
static char order[128];
static uint32_t selected_snapshot[3][4];
uint64_t emu_ns;

static int within(uint32_t a, uint32_t n, uint32_t start, uint32_t size)
{ return a>=start && (uint64_t)a+n<=(uint64_t)start+size; }

uint8_t *mem_host(uint32_t a, uint32_t n)
{
    if (within(a,n,TABLE,168*16)) return image+TABLE_ROM-BASE+a-TABLE;
    if (within(a,n,MANAGER_GLOBAL,4)) return manager_global+a-MANAGER_GLOBAL;
    if (within(a,n,SYNC_GLOBALS,8)) return sync_globals+a-SYNC_GLOBALS;
    for(unsigned i=0;i<3;i++)
        if(within(a,n,slot_buffers[i]-16,slot_sizes[i]+32))
            return payloads[i]+a-(slot_buffers[i]-16);
    if (within(a,n,NOTIFY,8)) return notify_ret+a-NOTIFY;
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
    int allowed=within(a,n,OBJ+200,212) || within(a,n,FRAME-2048,2080) || within(a,n,FLAGS,21);
    allowed|=reading && within(a,n,SOURCE,200);
    for(unsigned i=0;i<3;i++) allowed|=within(a,n,slot_buffers[i],slot_sizes[i]);
    if (monitoring && !allowed) {
        ++invalid_write;
        emu_abort(PC,"unexpected write %08x/%d",a,n);
    }
    uint8_t *p=mem_host(a,n);
    if(!p) emu_abort(PC,"unmapped write %08x",a);
    for(int i=0;i<n;i++) p[i]=(uint8_t)(v>>(8*i));
}
void mem_misaligned(uint32_t a,int n,int w) { emu_abort(PC,"misaligned %08x/%d/%d",a,n,w); }
static void record(char event)
{
    if(order_size+1>=sizeof order) emu_abort(PC,"event overflow");
    order[order_size++]=event; order[order_size]=0;
}
int hle_is_hook(uint32_t a)
{ return a==INIT || a==UPDATE || a==SETTING || a==GET_SERVICE || a==METHOD || a==CALLER+7 ||
         a==LOCK || a==UNLOCK || a==COPY || a==MARK || a==NOTIFY; }
int hle_check(cpu_t *c)
{
    uint32_t pc=c->regs[REG_PC], sp=c->regs[REG_SP], a=c->regs[REG_A0];
    if(pc==CALLER+7) { stopped=emu_stop=1; return 1; }
    if(pc==INIT) ++init_calls;
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
        ++updates; last_id=c->regs[REG_D0]; last_source=a; last_size=c->regs[REG_D0+1];
    }
    if(pc==LOCK) {
        if(locked || c->regs[REG_D0]!=UINT32_MAX) emu_abort(pc,"invalid lock request");
        record('L'); locked=!lock_fail; c->regs[REG_D0]=locked;
    }
    if(pc==UNLOCK) {
        if(!locked) emu_abort(pc,"unlock without acquisition");
        record('U'); locked=0;
    }
    if(pc==COPY || pc==MARK) {
        if(!locked) emu_abort(pc,"transfer outside modeled lock");
        record(pc==COPY?'C':'B');
        if(pc==COPY) ++copies;
        else {
            if(a!=OBSERVER || c->regs[REG_D0]!=last_id) emu_abort(pc,"wrong observer mark");
            ++marks;
        }
    }
    if(pc==NOTIFY) {
        if(locked || a!=OBSERVER || !(mem_rd(FLAGS+last_id/8,1)&(1u<<(last_id%8))))
            emu_abort(pc,"notification before unlock/mark");
        for(unsigned i=0;i<3;i++) if(slot_ids[i]==last_id) {
            unsigned count=last_size<slot_sizes[i]?last_size:slot_sizes[i];
            if(memcmp(mem_host(slot_buffers[i],count),mem_host(last_source,count),count))
                emu_abort(pc,"notification before payload copy");
        }
        ++notifications; record('N'); mem_wr(sp+64,c->regs[REG_MDR],4);
    }
    return 0;
}
void soc_tick(uint64_t cycles) { emu_ns+=cycles; }
uint64_t soc_next_event(void) { return emu_ns+1; }

static void setup(void)
{
    memset(cpus,0,sizeof cpus[0]); memset(ram,0,sizeof ram); monitoring=0;
    memset(payloads,0xa5,sizeof payloads);
    for(unsigned i=0;i<3;i++) memset(payloads[i]+16,0,slot_sizes[i]);
    memset(selected_snapshot,0,sizeof selected_snapshot);
    mem_wr(MANAGER_GLOBAL,MANAGER,4); mem_wr(SYNC_GLOBALS,LOCK,4); mem_wr(SYNC_GLOBALS+4,UNLOCK,4);
    mem_wr(MANAGER+8,TABLE,4); mem_wr(MANAGER+12,168,2);
    mem_wr(MANAGER+16,NODE,4); mem_wr(MANAGER+20,NODE,4);
    mem_wr(NODE,MANAGER+16,4); mem_wr(NODE+4,MANAGER+16,4); mem_wr(NODE+8,OBSERVER,4);
    mem_wr(OBSERVER+16,FLAGS,4);
    mem_wr(LOCK,0xf0,1); mem_wr(LOCK+1,0xfc,1);
    mem_wr(UNLOCK,0xf0,1); mem_wr(UNLOCK+1,0xfc,1);
    init_calls=updates=settings=invalid_write=stopped=emu_stop=0;
    locked=lock_fail=copies=marks=notifications=order_size=0; order[0]=0;
    reading=0;
}

static int execute(uint32_t target, unsigned mask, unsigned frame)
{
    mem_wr(CALLER,0xdd,1); mem_wr(CALLER+1,target-CALLER,4);
    mem_wr(CALLER+5,mask,1); mem_wr(CALLER+6,frame,1);
    cpu_t *c=&cpus[0]; c->running=1; c->irq_level=7; c->regs[REG_PC]=CALLER;
    c->regs[REG_SP]=FRAME;
    c->regs[REG_D0+2]=0x12345678; c->regs[REG_D0+3]=0x87654321;
    c->regs[REG_A0+2]=0x13572468; c->regs[REG_A0+3]=0x24681357;
    monitoring=1; cpu_run(200000,0); monitoring=0;
    if(!stopped || invalid_write || locked || c->regs[REG_SP]!=FRAME ||
       c->regs[REG_D0+2]!=0x12345678 || c->regs[REG_D0+3]!=0x87654321 ||
       c->regs[REG_A0+2]!=0x13572468 || c->regs[REG_A0+3]!=0x24681357) {
        fprintf(stderr,"target=%08x pc=%08x sp=%08x stop=%u invalid=%u order=%s\n",
                target,c->regs[REG_PC],c->regs[REG_SP],stopped,invalid_write,order);
        return 0;
    }
    for(unsigned i=0;i<3;i++) for(unsigned j=0;j<16;j++)
        if(payloads[i][j]!=0xa5 || payloads[i][16+slot_sizes[i]+j]!=0xa5) return 0;
    return 1;
}

static int run(unsigned selection, uint16_t mask)
{
    setup();
    mem_wr(OBJ+412,DESC,4); mem_wr(OBJ+416,selection,2); mem_wr(OBJ+420,AVAILABLE,4);
    for(unsigned i=0;i<13;i++) mem_wr(AVAILABLE+i,(mask>>i)&1,1);
    mem_wr(SERVICE,VTABLE,4); mem_wr(VTABLE+20,METHOD,4);
    mem_wr(METHOD,0xf0,1); mem_wr(METHOD+1,0xfc,1); /* rets */
    cpus[0].regs[REG_A0]=OBJ;
    if(!execute(DRAW,0xf0,84) || init_calls!=3 || updates!=3 || copies!=6 || marks!=3 || notifications!=3 ||
       strcmp(order,"LCULCULCULCBUNLCBUNLCBUN")) return 0;
    for(unsigned i=0;i<3;i++) {
        unsigned offset=slot_ids[i]==58?200:slot_ids[i]==0?388:400;
        if(memcmp(payloads[i]+16,mem_host(OBJ+offset,slot_sizes[i]),slot_sizes[i])) return 0;
    }
    for(unsigned i=0;i<21;i++) {
        unsigned expected=i==0?1:i==1?128:i==7?4:0;
        if(mem_rd(FLAGS+i,1)!=expected) return 0;
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

static const struct {
    const char *name;
    unsigned bytes, null_payload, invalid_id, fail_lock, no_manager, notify;
    unsigned copied, success;
    const char *order;
} contract_cases[] = {
    {"exact",188,0,0,0,0,1,188,1,"LCBUN"},
    {"oversized",200,0,0,0,0,1,188,1,"LCBUN"},
    {"short",7,0,0,0,0,1,7,1,"LCBUN"},
    {"zero_length",0,0,0,0,0,1,0,1,"LCBUN"},
    {"null_payload",188,1,0,0,0,1,0,0,""},
    {"invalid_id",188,0,1,0,0,1,0,0,""},
    {"lock_failure",188,0,0,1,0,1,0,0,"L"},
    {"no_manager",188,0,0,0,1,1,0,0,""},
    {"no_notify",188,0,0,0,0,0,188,1,"LCBU"},
};

static int run_contract(unsigned index, unsigned read)
{
    setup();
    reading=read;
    for(unsigned i=0;i<200;i++) mem_wr(SOURCE+i,read?0x5a:(i%251)+1,1);
    for(unsigned i=0;i<188;i++) payloads[2][16+i]=read?(i%251)+1:0x5a;
    lock_fail=contract_cases[index].fail_lock;
    if(contract_cases[index].no_manager) mem_wr(MANAGER_GLOBAL,0,4);
    cpu_t *c=&cpus[0];
    c->regs[REG_D0]=contract_cases[index].invalid_id?168:58;
    c->regs[REG_D0+1]=contract_cases[index].bytes;
    c->regs[REG_A0]=contract_cases[index].null_payload?0:SOURCE;
    c->regs[REG_A0+1]=contract_cases[index].notify;
    const char *expected_order=read?(contract_cases[index].success?"LCU":lock_fail?"L":""):contract_cases[index].order;
    if(!execute(read?INIT:UPDATE,read?0:0xa0,read?4:16) || c->regs[REG_D0]!=contract_cases[index].success ||
       strcmp(order,expected_order)) return 0;
    for(unsigned i=0;i<200;i++) {
        unsigned transferred=i<contract_cases[index].copied?(i%251)+1:0x5a;
        if(mem_rd(SOURCE+i,1)!=(read?transferred:(i%251)+1)) return 0;
        if(i<188 && payloads[2][16+i]!=(read?(i%251)+1:transferred)) return 0;
    }
    for(unsigned i=0;i<21;i++)
        if(mem_rd(FLAGS+i,1)!=(!read && i==7 && contract_cases[index].success?4u:0u)) return 0;
    for(unsigned i=0;i<2;i++) for(unsigned j=0;j<slot_sizes[i];j++)
        if(payloads[i][16+j]) return 0;
    return copies==contract_cases[index].success && marks==(!read && contract_cases[index].success) &&
           notifications==(!read && contract_cases[index].success && contract_cases[index].notify);
}
int main(int argc,char **argv)
{
    if(argc!=2) return 2;
    FILE *f=fopen(argv[1],"rb"); image=malloc(SIZE);
    if(!f || !image || fread(image,1,SIZE,f)!=SIZE || fgetc(f)!=EOF) return 2;
    fclose(f);
    for(unsigned i=0;i<13;i++) if(!run(i,0x1fff)) { fprintf(stderr,"case %u failed\n",i); return 1; }
    for(unsigned i=0;i<13;i++) if((0x1293u>>i)&1) if(!run(i,0x1293)) { fprintf(stderr,"sparse case %u failed\n",i); return 1; }
    for(unsigned i=0;i<sizeof contract_cases/sizeof contract_cases[0];i++)
        if(!run_contract(i,0)) { fprintf(stderr,"update contract %s failed; order=%s\n",contract_cases[i].name,order); return 1; }
    for(unsigned i=0;i<8;i++)
        if(!run_contract(i,1)) { fprintf(stderr,"read contract %s failed; order=%s\n",contract_cases[i].name,order); return 1; }
    printf("{\"cases\":19,\"stock_page_assembly_executed\":true,\"resource_rows_and_paging_verified\":true,"
           "\"modeled_services\":true,\"updates_per_case\":3,\"stack_and_callee_saved_preserved\":true,"
           "\"stock_gui_transfer_executed\":true,\"copied_payloads_verified\":true,\"stock_listener_bits_verified\":true,"
           "\"lock_copy_notify_order_verified\":true,\"service_contract_cases\":[");
    for(unsigned i=0;i<sizeof contract_cases/sizeof contract_cases[0];i++)
        printf("%s\"%s\"",i?",":"",contract_cases[i].name);
    printf("],\"read_contract_cases\":[");
    for(unsigned i=0;i<8;i++) printf("%s\"%s\"",i?",":"",contract_cases[i].name);
    puts("]}");
    free(image); return 0;
}
