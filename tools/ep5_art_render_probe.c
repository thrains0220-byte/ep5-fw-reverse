/* Execute stock ART assembly, GUI copies and notification queue operations. */
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
#define GUI_ENQUEUE 0x7ea0b817u
#define GUI_DEQUEUE 0x7ea0b96au
#define GUI_PRUNE_TARGET 0x7ea0bb28u
#define GUI_LOCK 0x7ea0c01du
#define GUI_UNLOCK 0x7ea0c041u
#define GUI_SIGNAL 0x7ea0bf8du
#define GUI_WAIT 0x7ea0bfebu
#define GUI_CLEAR_SIGNAL 0x7ea0bfb9u
#define GUI_RING 0x606e623cu
#define GUI_INDEX 0x606ea0bcu
#define GUI_MESSAGE (RAM + 0x5200u)
#define GUI_TARGET (RAM + 0x6000u)
#define GUI_VTABLE 0x7ec6e538u
#define GUI_PROVIDER_VTABLE (RAM + 0x6800u)
#define GUI_VIEW_VTABLE (RAM + 0x6c00u)
#define GUI_SNAPSHOT (RAM + 0x5740u)
#define GUI_PROVIDER (GUI_TARGET + 416u)
#define GUI_VIEW (RAM + 0x7110u)
#define GUI_CHILD_1 (RAM + 0x7120u)
#define GUI_CHILD_2 (RAM + 0x7130u)
#define GUI_LIST (RAM + 0x7140u)
#define GUI_NODE_1 (RAM + 0x7160u)
#define GUI_NODE_2 (RAM + 0x7170u)
#define GUI_GET_CHILDREN (RAM + 0x71a0u)
#define GUI_VIEW_EVENT (RAM + 0x71b0u)
#define GUI_DISPATCH 0x7ea15c5fu
#define GUI_EVENT 0x7ea14578u
#define GUI_REFRESH 0x7ea16b2au
#define GUI_TAKE_FLAGS 0x7ea14214u
#define OBSERVER_INIT 0x7ea1413au
#define OBSERVER_DEINIT 0x7ea14163u
#define OBSERVER_SET_TARGET 0x7ea141d3u
#define GUI_ALLOC 0x7ea236d0u
#define GUI_FREE 0x7ea236dcu

static uint8_t *image, ram[RAM_SIZE];
static uint8_t setting_ret[8] = {0xdf,0xa0,12}, service_ret[8] = {0xdf,0,4};
static uint8_t gui_lock_ret[8] = {0xdf,0x80,8}, gui_wait_ret[8] = {0xdf,0x80,16};
static uint8_t gui_signal_ret[8] = {0xdf,0,4};
static uint8_t gui_allocator_ret[8] = {0xdf,0,4};
static uint8_t gui_ring[500 * 32], gui_state[84];
static uint8_t manager_global[4], sync_globals[8], payloads[3][220];
static const uint32_t slot_ids[3] = {0,15,58};
static const uint32_t slot_buffers[3] = {0x606eb274u,0x606eb452u,0x606f1670u};
static const unsigned slot_sizes[3] = {12,12,188};
static unsigned init_calls, updates, settings, invalid_write, stopped, monitoring;
static unsigned locked, lock_fail, copies, marks, notifications, order_size;
static unsigned reading;
static unsigned gui_locked, gui_signals, gui_dequeuing, gui_refreshes, gui_refreshing;
static unsigned gui_view_events, gui_empty_children;
static unsigned gui_observer_lifecycle, gui_allocations, gui_frees;
static unsigned gui_pruning;
static uint8_t expected_dirty[21];
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
    if (within(a,n,GUI_RING,sizeof gui_ring)) return gui_ring+a-GUI_RING;
    if (within(a,n,GUI_INDEX,sizeof gui_state)) return gui_state+a-GUI_INDEX;
    if (within(a,n,GUI_LOCK,8)) return gui_lock_ret+a-GUI_LOCK;
    if (within(a,n,GUI_WAIT,8)) return gui_wait_ret+a-GUI_WAIT;
    if (within(a,n,GUI_UNLOCK,8)) return gui_signal_ret+a-GUI_UNLOCK;
    if (within(a,n,GUI_SIGNAL,8)) return gui_signal_ret+a-GUI_SIGNAL;
    if (within(a,n,GUI_CLEAR_SIGNAL,8)) return gui_signal_ret+a-GUI_CLEAR_SIGNAL;
    if (within(a,n,GUI_ALLOC,8)) return gui_allocator_ret+a-GUI_ALLOC;
    if (within(a,n,GUI_FREE,8)) return gui_allocator_ret+a-GUI_FREE;
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
    allowed|=gui_dequeuing && within(a,n,GUI_MESSAGE,28);
    allowed|=gui_refreshing && (within(a,n,GUI_SNAPSHOT,21) || within(a,n,GUI_LIST+16,4));
    allowed|=gui_observer_lifecycle && (within(a,n,MANAGER+16,8) ||
        within(a,n,NODE,12) || within(a,n,OBSERVER,24) || within(a,n,GUI_SNAPSHOT,21));
    allowed|=gui_locked && (within(a,n,GUI_RING,gui_pruning ? 64 : 32) || within(a,n,GUI_INDEX,4));
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
         a==LOCK || a==UNLOCK || a==COPY || a==MARK || a==NOTIFY || a==GUI_ENQUEUE ||
         a==GUI_LOCK || a==GUI_UNLOCK || a==GUI_SIGNAL || a==GUI_WAIT || a==GUI_CLEAR_SIGNAL ||
         a==GUI_REFRESH || a==GUI_GET_CHILDREN || a==GUI_EVENT ||
         a==GUI_VIEW_EVENT || a==GUI_TAKE_FLAGS || a==GUI_ALLOC || a==GUI_FREE; }
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
        if(pc==COPY && gui_pruning && gui_locked) {
            if(a!=GUI_RING || c->regs[REG_A0+1]!=GUI_RING+32 || c->regs[REG_D0]!=32)
                emu_abort(pc,"unexpected queue compaction");
            return 0;
        }
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
        ++notifications; record('N');
    }
    if(pc==GUI_ENQUEUE) {
        if(locked || gui_locked || c->regs[REG_D0]!=1 ||
           mem_rd(sp+28,4)!=0x1900u || mem_rd(sp+32,2)!=0xfffeu ||
           mem_rd(sp+36,4)!=GUI_TARGET || mem_rd(sp+40,4) ||
           mem_rd(sp+44,4) || mem_rd(sp+48,4) || mem_rd(sp+52,4))
            emu_abort(pc,"unexpected GUI notification envelope");
    }
    if(pc==GUI_LOCK || pc==GUI_WAIT) {
        if(gui_locked || locked || (pc==GUI_WAIT && !gui_dequeuing))
            emu_abort(pc,"unexpected GUI queue lock");
        if(pc==GUI_LOCK) gui_locked=1;
        c->regs[REG_D0]=1;
    }
    if(pc==GUI_UNLOCK || pc==GUI_SIGNAL || pc==GUI_CLEAR_SIGNAL) {
        if(!gui_locked || locked || (pc==GUI_CLEAR_SIGNAL && !gui_dequeuing && !gui_pruning))
            emu_abort(pc,"unexpected GUI queue signal");
        if(pc==GUI_SIGNAL) ++gui_signals;
        if(pc==GUI_UNLOCK) gui_locked=0;
        c->regs[REG_D0]=1;
    }
    if(pc==GUI_REFRESH) {
        if(!gui_refreshing || locked || gui_locked || a!=GUI_TARGET || c->regs[REG_D0]!=0x1900u ||
           c->regs[REG_D0+1] || c->regs[REG_A0+1])
            emu_abort(pc,"incorrect GUI refresh dispatch");
        ++gui_refreshes;
    }
    if(pc==GUI_GET_CHILDREN) {
        if(!gui_refreshing || a!=GUI_PROVIDER)
            emu_abort(pc,"incorrect GUI collection receiver");
        c->regs[REG_A0]=GUI_LIST;
    }
    if(pc==GUI_TAKE_FLAGS && (!gui_refreshing || a!=OBSERVER))
        emu_abort(pc,"unexpected GUI observer");
    if(pc==GUI_ALLOC || pc==GUI_FREE) {
        if(!gui_observer_lifecycle || c->regs[REG_D0]!=5 || c->regs[REG_D0+1])
            emu_abort(pc,"unexpected GUI heap call");
        const uint32_t objects[]={NODE,GUI_SNAPSHOT,FLAGS};
        if(pc==GUI_ALLOC) {
            if(gui_allocations>=3 || a!=(gui_allocations==0 ? 12u : 21u))
                emu_abort(pc,"unexpected GUI allocation size");
            c->regs[REG_A0]=objects[gui_allocations++];
        } else {
            if(gui_frees>=3 || a!=objects[gui_frees] ||
               mem_rd(MANAGER+16,4)!=MANAGER+16 || mem_rd(MANAGER+20,4)!=MANAGER+16)
                emu_abort(pc,"observer storage freed before unlink");
            ++gui_frees;
        }
    }
    if((pc==GUI_EVENT && c->regs[REG_D0]==0x1902u) || pc==GUI_VIEW_EVENT) {
        static const uint32_t views[]={GUI_CHILD_1,GUI_CHILD_2,GUI_VIEW};
        if(!gui_refreshing || locked || gui_locked || c->regs[REG_D0+1]!=OBSERVER ||
           c->regs[REG_A0+1] ||
           memcmp(mem_host(GUI_SNAPSHOT,sizeof expected_dirty),expected_dirty,sizeof expected_dirty))
            emu_abort(pc,"invalid GUI observer snapshot or event");
        for(unsigned i=0;i<sizeof expected_dirty;i++)
            if(mem_rd(FLAGS+i,1)) emu_abort(pc,"dirty flags were not cleared before dispatch");
        if(pc==GUI_EVENT) {
            if(a!=GUI_TARGET || gui_view_events) emu_abort(pc,"unexpected GUI root view");
            ++gui_view_events;
            /* Stop at the base dispatcher for the root's internal event. The
             * concrete view's handler and drawing state are outside this test. */
            c->regs[REG_PC]=c->regs[REG_MDR];
            return 1;
        }
        if(gui_empty_children || c->regs[REG_D0]!=0x1901u ||
           gui_view_events<1 || gui_view_events>3 || a!=views[gui_view_events-1])
            emu_abort(pc,"unexpected GUI child view order");
        ++gui_view_events;
        c->regs[REG_D0]=0;
    }
    return 0;
}
void soc_tick(uint64_t cycles) { emu_ns+=cycles; }
uint64_t soc_next_event(void) { return emu_ns+1; }

static void setup(void)
{
    memset(cpus,0,sizeof cpus[0]); memset(ram,0,sizeof ram); monitoring=0;
    memset(gui_ring,0,sizeof gui_ring); memset(gui_state,0,sizeof gui_state);
    memset(payloads,0xa5,sizeof payloads);
    for(unsigned i=0;i<3;i++) memset(payloads[i]+16,0,slot_sizes[i]);
    memset(selected_snapshot,0,sizeof selected_snapshot);
    mem_wr(MANAGER_GLOBAL,MANAGER,4); mem_wr(SYNC_GLOBALS,LOCK,4); mem_wr(SYNC_GLOBALS+4,UNLOCK,4);
    mem_wr(MANAGER+8,TABLE,4); mem_wr(MANAGER+12,168,2);
    mem_wr(MANAGER+16,NODE,4); mem_wr(MANAGER+20,NODE,4);
    mem_wr(NODE,MANAGER+16,4); mem_wr(NODE+4,MANAGER+16,4); mem_wr(NODE+8,OBSERVER,4);
    mem_wr(OBSERVER+8,GUI_TARGET,4);
    mem_wr(OBSERVER+12,GUI_SNAPSHOT,4);
    mem_wr(OBSERVER+16,FLAGS,4);
    mem_wr(OBSERVER+20,21,4);
    mem_wr(GUI_TARGET,GUI_VTABLE,4);
    mem_wr(GUI_TARGET + 412,GUI_VIEW,4);
    mem_wr(GUI_TARGET + 2008,OBSERVER,4);
    mem_wr(GUI_PROVIDER,GUI_PROVIDER_VTABLE,4);
    mem_wr(GUI_PROVIDER_VTABLE + 440,GUI_GET_CHILDREN,4);
    mem_wr(GUI_VIEW,GUI_VIEW_VTABLE,4);
    mem_wr(GUI_CHILD_1,GUI_VIEW_VTABLE,4);
    mem_wr(GUI_CHILD_2,GUI_VIEW_VTABLE,4);
    mem_wr(GUI_VIEW_VTABLE+408,GUI_VIEW_EVENT,4);
    mem_wr(GUI_LIST+8,GUI_NODE_1,4);
    mem_wr(GUI_NODE_1+4,GUI_NODE_2,4);
    mem_wr(GUI_NODE_1+8,GUI_CHILD_1,4);
    mem_wr(GUI_NODE_2+4,GUI_LIST+4,4);
    mem_wr(GUI_NODE_2+8,GUI_CHILD_2,4);
    const uint32_t methods[]={GUI_GET_CHILDREN,GUI_VIEW_EVENT};
    for(unsigned i=0;i<sizeof methods/sizeof *methods;i++)
        mem_wr(methods[i],0x000000de,4); /* retf [],0 */
    mem_wr(LOCK,0xf0,1); mem_wr(LOCK+1,0xfc,1);
    mem_wr(UNLOCK,0xf0,1); mem_wr(UNLOCK+1,0xfc,1);
    init_calls=updates=settings=invalid_write=stopped=emu_stop=0;
    locked=lock_fail=copies=marks=notifications=order_size=0; order[0]=0;
    reading=0;
    gui_locked=gui_signals=gui_dequeuing=gui_refreshes=gui_refreshing=0;
    gui_view_events=gui_empty_children=0;
    gui_observer_lifecycle=gui_allocations=gui_frees=0;
    gui_pruning=0;
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
    if(!stopped || invalid_write || locked || gui_locked || c->regs[REG_SP]!=FRAME ||
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

static int notification_queued_once(void)
{
    return gui_signals==1 && mem_rd(GUI_RING,1)==1 &&
        mem_rd(GUI_INDEX,2)==0 && mem_rd(GUI_INDEX+2,2)==1 &&
        mem_rd(GUI_RING+4,4)==0x1900u && mem_rd(GUI_RING+12,4)==GUI_TARGET;
}

static int consume_notification(int empty_children)
{
    if(!notification_queued_once()) return 0;
    stopped=emu_stop=0;
    gui_dequeuing=1;
    cpus[0].regs[REG_D0]=0;
    cpus[0].regs[REG_A0]=GUI_MESSAGE;
    if(!execute(GUI_DEQUEUE,0xf0,20) || cpus[0].regs[REG_D0]!=1) return 0;
    gui_dequeuing=0;
    if(mem_rd(GUI_RING,1) || mem_rd(GUI_INDEX,2)!=1 ||
       mem_rd(GUI_INDEX+2,2)!=1 || mem_rd(GUI_MESSAGE,4)!=0x1900u ||
       mem_rd(GUI_MESSAGE+8,4)!=GUI_TARGET) return 0;

    /* Drive the real dispatch and base refresh with the dequeued message.
     * The refresh must snapshot the observer before dispatching view events. */
    stopped=emu_stop=0;
    gui_empty_children=empty_children;
    if(empty_children) mem_wr(GUI_LIST+8,0,4);
    memcpy(expected_dirty,mem_host(FLAGS,sizeof expected_dirty),sizeof expected_dirty);
    gui_refreshing=1;
    cpus[0].regs[REG_A0]=0; /* a targeted message must not use the current menu */
    cpus[0].regs[REG_A0+1]=GUI_MESSAGE;
    if(!execute(GUI_DISPATCH,0xa0,12) || gui_refreshes!=1 ||
       cpus[0].regs[REG_D0]!=(empty_children ? UINT32_MAX : 0) ||
       gui_view_events!=(empty_children ? 1u : 4u))
        return 0;
    gui_refreshing=0;
    return 1;
}

static int run_observer_lifecycle(void)
{
    setup();
    mem_wr(MANAGER+16,MANAGER+16,4);
    mem_wr(MANAGER+20,MANAGER+16,4);
    memset(mem_host(OBSERVER,24),0xa5,24);
    memset(mem_host(FLAGS,21),0xa5,21);
    memset(mem_host(GUI_SNAPSHOT,21),0xa5,21);
    gui_observer_lifecycle=1;
    cpus[0].regs[REG_A0]=OBSERVER;
    if(!execute(OBSERVER_INIT,0x20,8) || cpus[0].regs[REG_A0]!=OBSERVER ||
       gui_allocations!=3 || gui_frees || mem_rd(MANAGER+16,4)!=NODE ||
       mem_rd(MANAGER+20,4)!=NODE || mem_rd(NODE+8,4)!=OBSERVER ||
       mem_rd(OBSERVER+8,4) || mem_rd(OBSERVER+12,4)!=GUI_SNAPSHOT ||
       mem_rd(OBSERVER+16,4)!=FLAGS || mem_rd(OBSERVER+20,4)!=21)
        return 0;
    for(unsigned i=0;i<21;i++)
        if(mem_rd(FLAGS+i,1) || mem_rd(GUI_SNAPSHOT+i,1)) return 0;

    stopped=emu_stop=0;
    cpus[0].regs[REG_A0]=OBSERVER;
    cpus[0].regs[REG_A0+1]=GUI_TARGET;
    if(!execute(OBSERVER_SET_TARGET,0,0) || mem_rd(OBSERVER+8,4)!=GUI_TARGET)
        return 0;

    stopped=emu_stop=0;
    cpus[0].regs[REG_D0]=58;
    cpus[0].regs[REG_D0+1]=188;
    cpus[0].regs[REG_A0]=SOURCE;
    cpus[0].regs[REG_A0+1]=1;
    if(!execute(UPDATE,0xa0,16) || copies!=1 || marks!=1 || notifications!=1 ||
       !consume_notification(0))
        return 0;

    stopped=emu_stop=0;
    cpus[0].regs[REG_A0]=OBSERVER;
    if(!execute(OBSERVER_DEINIT,0,0) || gui_frees!=3 ||
       mem_rd(OBSERVER+12,4) || mem_rd(OBSERVER+16,4))
        return 0;

    /* Further publication goes through the stock update service but must
     * no longer notify the unlinked observer. There are no pending events. */
    stopped=emu_stop=0;
    cpus[0].regs[REG_D0]=58;
    cpus[0].regs[REG_D0+1]=188;
    cpus[0].regs[REG_A0]=SOURCE;
    cpus[0].regs[REG_A0+1]=1;
    const unsigned earlier_copies=copies;
    return execute(UPDATE,0xa0,16) && copies==earlier_copies+1 && marks==1 && notifications==1 &&
        gui_signals==1 && mem_rd(GUI_INDEX,2)==mem_rd(GUI_INDEX+2,2);
}

static int run_target_prune(void)
{
    setup();
    cpus[0].regs[REG_D0]=58;
    cpus[0].regs[REG_D0+1]=188;
    cpus[0].regs[REG_A0]=SOURCE;
    cpus[0].regs[REG_A0+1]=1;
    if(!execute(UPDATE,0xa0,16) || !notification_queued_once()) return 0;

    /* Keep a same-code message for a different target behind the old view's
     * refresh. The stock prune must remove by target and preserve its bytes. */
    memcpy(gui_ring+32,gui_ring,32);
    mem_wr(GUI_RING+32+12,GUI_VIEW,4);
    mem_wr(GUI_RING+32+16,0x11223344,4);
    mem_wr(GUI_INDEX+2,2,2);
    uint8_t retained[32];
    memcpy(retained,gui_ring+32,sizeof retained);

    stopped=emu_stop=0;
    gui_pruning=1;
    cpus[0].regs[REG_A0]=GUI_TARGET;
    if(!execute(GUI_PRUNE_TARGET,0xf0,28) || mem_rd(GUI_INDEX,2)!=0 ||
       mem_rd(GUI_INDEX+2,2)!=1 || mem_rd(GUI_RING+32,1) ||
       memcmp(gui_ring,retained,sizeof retained))
        return 0;
    gui_pruning=0;

    stopped=emu_stop=0;
    gui_dequeuing=1;
    cpus[0].regs[REG_D0]=0;
    cpus[0].regs[REG_A0]=GUI_MESSAGE;
    if(!execute(GUI_DEQUEUE,0xf0,20) || cpus[0].regs[REG_D0]!=1 ||
       memcmp(mem_host(GUI_MESSAGE,28),retained+4,28) ||
       mem_rd(GUI_INDEX,2)!=mem_rd(GUI_INDEX+2,2))
        return 0;
    gui_dequeuing=0;
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
    return consume_notification(0);
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
           notifications==(!read && contract_cases[index].success && contract_cases[index].notify) &&
           (notifications ? consume_notification(index==0) : !gui_signals && !mem_rd(GUI_INDEX+2,2));
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
    if(!run_observer_lifecycle()) { fprintf(stderr,"observer lifecycle failed\n"); return 1; }
    if(!run_target_prune()) { fprintf(stderr,"target notification prune failed\n"); return 1; }
    printf("{\"cases\":19,\"stock_page_assembly_executed\":true,\"resource_rows_and_paging_verified\":true,"
           "\"modeled_services\":true,\"updates_per_case\":3,\"stack_and_callee_saved_preserved\":true,"
           "\"stock_gui_transfer_executed\":true,\"copied_payloads_verified\":true,\"stock_listener_bits_verified\":true,"
           "\"lock_copy_notify_order_verified\":true,\"stock_notification_queue_verified\":true,"
           "\"stock_notification_dispatch_verified\":true,\"stock_observer_snapshot_verified\":true,"
           "\"stock_base_refresh_verified\":true,\"refresh_cases\":[\"children_and_view\",\"empty_children\"],"
           "\"stock_observer_lifecycle_verified\":true,\"stock_target_prune_verified\":true,"
           "\"notification_code\":6400,\"service_contract_cases\":[");
    for(unsigned i=0;i<sizeof contract_cases/sizeof contract_cases[0];i++)
        printf("%s\"%s\"",i?",":"",contract_cases[i].name);
    printf("],\"read_contract_cases\":[");
    for(unsigned i=0;i<8;i++) printf("%s\"%s\"",i?",":"",contract_cases[i].name);
    puts("]}");
    free(image); return 0;
}
