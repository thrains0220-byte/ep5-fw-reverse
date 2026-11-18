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
#define FILE_LOOP 0x7e28dd2fu
#define FILE_CURMSG 0x6057a108u
#define QUEUE_READ 0x7e131208u
#define FILE_REPLY 0x7e2952efu
#define READ_PARAMS (STACK + 0x100u)
#define REPLY_QUEUE 0x33u
#define REPLY_COOKIE 0x544f4b4eu
#define CORE_TABLE 0x8ff00004u
#define CORE_STATE (STACK + 0x300u)
#define CORE_FLAGS (STACK + 0x400u)
#define TASK_HEAD (STACK + 0x420u)
#define TASK_OBJECT (STACK + 0x440u)
#define QUEUE_CONFIG (STACK + 0x600u)
#define QUEUE_INDEX (STACK + 0x640u)
#define QUEUE_OBJECT (STACK + 0x700u)
#define QUEUE_RING (STACK + 0x780u)
#define POST_CALL (STACK + 0x800u)
#define POST_END (POST_CALL + 7u)
#define POST_BUFFER (STACK + 0x820u)
#define WAIT_TASK (STACK + 0x900u)
#define WAIT_BUFFER (STACK + 0xa00u)
#define POST_NATIVE 0x7e118051u
#define POLL_NATIVE 0x7e295329u
#define POST_CONTEXT 0x7e1117d8u
#define SCHED_LOCK 0x7e112c44u
#define SCHED_UNLOCK 0x7e112cbbu
#define QUEUE_COPY 0x7e117161u
#define TASK_READY 0x7e114e06u
#define TASK_RESCHEDULE 0x7e11683bu
static uint8_t *image, ram[65536];
static int direct, scenario, stopped, opened, read_calls, closed;
static int file_loop, received, replies;
static int file_post, post_full, post_waiter, post_locked, post_copy_count, waiter_ready;
static int file_poll, poll_has_message, rescheduled;
static uint32_t current_message, receive_buffer, receive_stack;
static uint32_t read_count;
uint64_t emu_ns;

/* The normal file wrappers and task selector execute from the E-P5 image.
 * Backend calls, queue transport and diagnostic prints are substitutes. */
static const struct hook { uint32_t pc; uint8_t ret[8]; } hooks[] = {
    {0x7e3d299a, {0xdf,0,4}}, {0x7e3d29a4, {0xdf,0,4}}, /* debug prints */
    {0x7e2960db, {0xdf,0xf0,64}}, {0x7e296da5, {0xdf,0xf0,20}},
    {0x7e29640e, {0xdf,0xb0,16}}, {0x7e13452b, {0xdf,0xc0,12}},
    {0x7e3fd443, {0xdf,0,4}}, {0x7e3fd94a, {0xdf,0,0}}, {0x7e3fd922, {0xdf,0x80,4}},
    {QUEUE_READ, {0xdf,0xf0,20}}, {FILE_REPLY, {0xdf,0xe0,48}},
    {POST_CONTEXT, {0xdf,0x80,4}},
    {SCHED_LOCK, {0xf0,0xfc}}, {SCHED_UNLOCK, {0xf0,0xfc}},
    {QUEUE_COPY, {0xdf,0x80,4}},
    {TASK_READY, {0xdf,0x20,4}}, {TASK_RESCHEDULE, {0xdf,0xb0,16}},
};
static int within(uint32_t a, uint32_t n, uint32_t b, uint32_t bytes)
{ return a >= b && (uint64_t)a+n <= (uint64_t)b+bytes; }

uint8_t *mem_host(uint32_t a, uint32_t n)
{
    for (size_t i=0; i<sizeof hooks/sizeof *hooks; ++i)
        if (!(file_poll && hooks[i].pc==QUEUE_READ) && within(a,n,hooks[i].pc,8))
            return (uint8_t *)hooks[i].ret+(a-hooks[i].pc);
    if (within(a,n,BASE,BYTES)) return image+(a-BASE);
    if (within(a,n,STACK,sizeof ram)) return ram+(a-STACK);
    return NULL;
}
uint32_t mem_rd(uint32_t a, int n)
{
    if (a==FILE_CURMSG && n==4 && file_loop) return current_message;
    if (a==0x8050 && n==4) return 0; /* model CPU 0 */
    if (a==CORE_TABLE && n==4) return CORE_STATE;
    uint8_t *p=mem_host(a,n); uint32_t v=0;
    if (!p) emu_abort(PC,"unmapped read %08x",a);
    for (int i=0;i<n;i++) v|=(uint32_t)p[i]<<(8*i);
    return v;
}
void mem_wr(uint32_t a,uint32_t v,int n)
{
    if (a==FILE_CURMSG && n==4 && file_loop) { current_message=v; return; }
    if (!within(a,n,STACK,sizeof ram)) emu_abort(PC,"write outside stack %08x",a);
    for (int i=0;i<n;i++) ram[a-STACK+i]=(uint8_t)(v>>(8*i));
}
void mem_misaligned(uint32_t a,int n,int wr) { emu_abort(PC,"misaligned %08x/%d/%d",a,n,wr); }
void soc_tick(uint64_t cycles) { emu_ns+=cycles; }
uint64_t soc_next_event(void) { return emu_ns+1; }
int hle_is_hook(uint32_t pc)
{
    if (pc==END || pc==SELECTOR_END || pc==POST_END) return 1;
    for (size_t i=0;i<sizeof hooks/sizeof *hooks;i++)
        if (pc==hooks[i].pc && !(file_poll && pc==QUEUE_READ)) return 1;
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

/* Stock FILEFGND runs its receive, dispatch and reply code. Model only the
 * queue transport and read backend, never an actual camera or mounted card. */
static int check_file_loop(uint32_t *r, uint32_t pc)
{
    uint32_t a=r[REG_A0];
    switch (pc) {
    case QUEUE_READ: {
        uint32_t buffer=mem_rd(a,4);
        expect(r[0]==mem_rd(0x7e11f938,2) && r[1]==UINT32_MAX &&
               mem_rd(a+4,4)==16 && !current_message);
        expect(within(buffer,16,STACK,sizeof ram));
        if (!received) {
            receive_buffer=buffer;
            receive_stack=r[REG_SP];
        }
        expect(buffer==receive_buffer && r[REG_SP]==receive_stack);
        if (received==2) {
            expect(read_calls==1 && replies==1 && mem_rd(READ_PARAMS,4)==7);
            stopped=emu_stop=1;
            return 1;
        }
        expect(!read_calls && !replies);
        /* First wake with a zero message, then hand in an ordinary read. */
        mem_wr(buffer,received ? REPLY_QUEUE : 0,4);
        mem_wr(buffer+4,received ? REPLY_COOKIE : 0,4);
        mem_wr(buffer+8,received ? 0x10005 : 0,4);
        mem_wr(buffer+12,received ? READ_PARAMS : 0,4);
        ++received;
        r[0]=0;
        break;
    }
    case 0x7e296da5:
        expect(received==2 && !read_calls && current_message==receive_buffer &&
               a==DEST && r[0]==1 && r[1]==32 && r[REG_A0+1]==HANDLE);
        ++read_calls;
        r[0]=7;
        break;
    case FILE_REPLY:
        expect(received==2 && read_calls==1 && !replies &&
               r[0]==REPLY_QUEUE && r[1]==12 && r[REG_A0+1]==UINT32_MAX &&
               mem_rd(a,2)==0 && mem_rd(a+4,4)==REPLY_COOKIE &&
               mem_rd(a+8,4)==READ_PARAMS && mem_rd(READ_PARAMS,4)==7);
        ++replies;
        r[0]=0;
        break;
    default:
        emu_abort(pc,"unexpected FILEFGND hook");
    }
    return 0;
}

/* Run the local queue sender with a synthetic kernel's queue and task state.
 * Only context validation, scheduler locking and the byte copy are modeled. */
static int check_file_post(uint32_t *r, uint32_t pc)
{
    uint32_t destination=r[REG_A0], source=r[REG_A0+1], length=r[0];
    switch (pc) {
    case POST_CONTEXT: r[0]=0; break;
    case SCHED_LOCK:
        expect(!post_locked);
        post_locked=1;
        break;
    case SCHED_UNLOCK:
        expect(post_locked);
        post_locked=0;
        break;
    case QUEUE_COPY:
        expect(post_locked && !post_full && post_copy_count<2 &&
               (post_waiter ? (destination==WAIT_BUFFER && !post_copy_count && length==16) :
                (destination==QUEUE_RING+(post_copy_count ? 4 : 0) &&
                 length==(post_copy_count ? 16 : 4))));
        for (uint32_t i=0;i<length;i++)
            mem_wr(destination+i,mem_rd(source+i,1),1);
        ++post_copy_count;
        break;
    case TASK_READY:
        expect(post_waiter && post_locked && destination==WAIT_TASK &&
               !waiter_ready && mem_rd(WAIT_TASK+12,2)==2);
        waiter_ready=1;
        break;
    case TASK_RESCHEDULE:
        expect(post_waiter && post_locked && waiter_ready);
        break;
    case POST_END:
        expect(!post_locked && r[REG_SP]==STACK+0xf000 &&
               r[0]==(post_full ? (uint32_t)-50 : 0) &&
               post_copy_count==(post_full ? 0 : post_waiter ? 1 : 2) &&
               mem_rd(QUEUE_OBJECT+52,4)==(post_waiter ? 0 : 1) &&
               mem_rd(QUEUE_OBJECT+48,4)==(post_waiter ? 32 : 12));
        if (post_waiter) {
            expect(waiter_ready && mem_rd(QUEUE_OBJECT+12,4)==QUEUE_OBJECT+12 &&
                   mem_rd(QUEUE_OBJECT+16,4)==QUEUE_OBJECT+12 &&
                   mem_rd(WAIT_TASK+64,4)==0 && mem_rd(WAIT_TASK+96,4)==16);
            for (unsigned i=0;i<16;i+=4)
                expect(!mem_rd(WAIT_BUFFER+i,4));
        } else if (!post_full) {
            expect(mem_rd(QUEUE_RING,4)==16);
            for (unsigned i=4;i<20;i+=4)
                expect(!mem_rd(QUEUE_RING+i,4));
        }
        stopped=emu_stop=1;
        return 1;
    default:
        emu_abort(pc,"unexpected local queue hook");
    }
    return 0;
}

/* Execute the local nonblocking receive all the way through its wrappers.
 * The actual ring traversal, empty detection and return translation run. */
static int check_file_poll(uint32_t *r, uint32_t pc)
{
    switch (pc) {
    case POST_CONTEXT: r[0]=0; break;
    case SCHED_LOCK:
        expect(!post_locked);
        post_locked=1;
        break;
    case SCHED_UNLOCK:
        expect(post_locked);
        post_locked=0;
        break;
    case QUEUE_COPY: {
        uint32_t length=r[0], to=r[REG_A0], from=r[REG_A0+1];
        expect(post_locked && poll_has_message && post_copy_count<2);
        expect(post_copy_count ? from==QUEUE_RING+4 && length==16 && to==POST_BUFFER :
               from==QUEUE_RING && length==4 && within(to,4,STACK,sizeof ram));
        for (uint32_t i=0;i<length;++i)
            mem_wr(to+i,mem_rd(from+i,1),1);
        ++post_copy_count;
        break;
    }
    case TASK_RESCHEDULE:
        expect(post_locked && poll_has_message && post_copy_count==2 && !rescheduled);
        rescheduled=1;
        break;
    case POST_END:
        expect(!post_locked && r[REG_SP]==STACK+0xf000 &&
               r[0]==(poll_has_message ? 0u : (uint32_t)-2) &&
               post_copy_count==(poll_has_message ? 2 : 0) && rescheduled==poll_has_message &&
               !mem_rd(QUEUE_OBJECT+52,4) && mem_rd(QUEUE_OBJECT+48,4)==32 &&
               mem_rd(QUEUE_OBJECT+40,4)==QUEUE_RING+(poll_has_message ? 20 : 0));
        for (uint32_t i=0;i<16;i+=4)
            expect(mem_rd(POST_BUFFER+i,4)==(poll_has_message ? mem_rd(QUEUE_RING+4+i,4) : UINT32_MAX));
        stopped=emu_stop=1;
        return 1;
    default: emu_abort(pc,"unexpected file-poll hook");
    }
    return 0;
}

int hle_check(cpu_t *c)
{
    uint32_t *r=c->regs, pc=r[REG_PC], a=r[REG_A0], b=r[REG_A0+1];
    if (file_loop) return check_file_loop(r,pc);
    if (file_poll) return check_file_poll(r,pc);
    if (file_post) return check_file_post(r,pc);
    if (pc==END || pc==SELECTOR_END) { stopped=emu_stop=1; return 1; }
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
    if (argc==5 && (!strcmp(argv[4],"file-post") || !strcmp(argv[4],"file-poll"))) {
        uint32_t channel=mem_rd(0x7e11f938,2);
        expect(channel==0x22);
        file_poll=!strcmp(argv[4],"file-poll");
        file_post=!file_poll;
        poll_has_message=file_poll && scenario==1;
        post_full=file_post && scenario==1;
        post_waiter=file_post && scenario==2;
        mem_wr(CORE_STATE+16,CORE_FLAGS,4);
        mem_wr(CORE_STATE+28,CORE_FLAGS,4);
        mem_wr(CORE_STATE+60,QUEUE_CONFIG,4);
        mem_wr(CORE_STATE+96,TASK_HEAD,4);
        mem_wr(CORE_STATE+232,QUEUE_INDEX,4);
        mem_wr(CORE_STATE+380,2,4);
        mem_wr(TASK_HEAD,TASK_OBJECT,4);
        mem_wr(TASK_OBJECT+16,0x12,2);
        mem_wr(QUEUE_CONFIG+26,channel,2);
        mem_wr(QUEUE_INDEX+4*(channel-1),QUEUE_OBJECT,4);
        mem_wr(QUEUE_OBJECT,1,2);
        mem_wr(QUEUE_OBJECT+4,QUEUE_OBJECT+4,4);
        mem_wr(QUEUE_OBJECT+12,post_waiter ? WAIT_TASK : QUEUE_OBJECT+12,4);
        mem_wr(QUEUE_OBJECT+16,post_waiter ? WAIT_TASK : QUEUE_OBJECT+12,4);
        mem_wr(QUEUE_OBJECT+24,16,4);
        mem_wr(QUEUE_OBJECT+32,QUEUE_RING,4);
        mem_wr(QUEUE_OBJECT+36,QUEUE_RING+((post_full || poll_has_message) ? 20 : 0),4);
        mem_wr(QUEUE_OBJECT+40,QUEUE_RING,4);
        mem_wr(QUEUE_OBJECT+44,QUEUE_RING+32,4);
        mem_wr(QUEUE_OBJECT+48,(post_full || poll_has_message) ? 12 : 32,4);
        mem_wr(QUEUE_OBJECT+52,(post_full || poll_has_message) ? 1 : 0,4);
        if (file_poll) {
            for (uint32_t i=0;i<16;i+=4)
                mem_wr(POST_BUFFER+i,UINT32_MAX,4);
            if (poll_has_message) {
                mem_wr(QUEUE_RING,16,4);
                mem_wr(QUEUE_RING+4,REPLY_QUEUE,4);
                mem_wr(QUEUE_RING+8,REPLY_COOKIE,4);
                mem_wr(QUEUE_RING+12,0x10005,4);
                mem_wr(QUEUE_RING+16,READ_PARAMS,4);
            }
        }
        if (post_waiter) {
            mem_wr(WAIT_TASK,QUEUE_OBJECT+12,4);
            mem_wr(WAIT_TASK+4,QUEUE_OBJECT+12,4);
            mem_wr(WAIT_TASK+12,4,2);
            mem_wr(WAIT_TASK+16,0x12,2);
            mem_wr(WAIT_TASK+64,UINT32_MAX,4);
            mem_wr(WAIT_TASK+100,WAIT_BUFFER,4);
            for (unsigned i=0;i<16;i+=4)
                mem_wr(WAIT_BUFFER+i,UINT32_MAX,4);
        }
        /* Native CALL, saving the registers and reserving the stock frame. */
        mem_wr(POST_CALL,0xdd,1);
        mem_wr(POST_CALL+1,(file_poll ? POLL_NATIVE : POST_NATIVE)-POST_CALL,4);
        mem_wr(POST_CALL+5,file_poll ? 0xe0 : 0xf0,1);
        mem_wr(POST_CALL+6,file_poll ? 48 : 40,1);
        cpus[0].regs[REG_PC]=POST_CALL;
        cpus[0].regs[REG_SP]=STACK+0xf000;
        cpus[0].regs[REG_A0]=POST_BUFFER;
        cpus[0].regs[REG_A0+1]=0;
        cpus[0].regs[0]=channel;
        cpus[0].regs[1]=16;
        cpus[0].running=1; cpus[0].irq_level=7;
        cpu_run(5000,0);
        if (file_poll)
            printf("{\"message_delivered\":%s,\"result\":%d,\"returned\":%s}\n",
                   poll_has_message?"true":"false",(int32_t)cpus[0].regs[0],stopped?"true":"false");
        else
            printf("{\"queue_full\":%s,\"waiter_ready\":%s,\"result\":%d,\"returned\":%s}\n",
                   post_full?"true":"false",waiter_ready?"true":"false",(int32_t)cpus[0].regs[0],
                   stopped?"true":"false");
        free(image);
        return stopped?0:1;
    }
    if (argc==5 && !strcmp(argv[4],"file-loop")) {
        file_loop=1;
        mem_wr(READ_PARAMS,UINT32_MAX,4);
        mem_wr(READ_PARAMS+4,DEST,4);
        mem_wr(READ_PARAMS+8,1,4);
        mem_wr(READ_PARAMS+12,32,4);
        mem_wr(READ_PARAMS+16,HANDLE,4);
        cpus[0].regs[REG_PC]=FILE_LOOP;
        cpus[0].regs[REG_SP]=STACK+0xf000;
        cpus[0].running=1; cpus[0].irq_level=7;
        cpu_run(5000,0);
        printf("{\"messages\":%d,\"backend_reads\":%d,\"replies\":%d,\"returned_to_receive\":%s}\n",
               received,read_calls,replies,stopped?"true":"false");
        free(image);
        return stopped?0:1;
    }
    if (argc==5 && !strcmp(argv[4],"selector")) {
        cpus[0].regs[REG_PC]=0x7e3fcb10; cpus[0].regs[REG_SP]=STACK+0xf000;
        cpus[0].regs[0]=direct; cpus[0].regs[1]=scenario;
        cpus[0].running=1; cpus[0].irq_level=7;
        cpu_run(5000,0);
        printf("%u\n",cpus[0].regs[0]);
        free(image); return stopped && cpus[0].regs[REG_SP]==STACK+0xf000 ? 0:1;
    }
    /* The stock selector reads the current task ID through the CPU-0 task
     * record. Model FILEFGND or another task without replacing the selector. */
    mem_wr(CORE_STATE+28,CORE_FLAGS,4);
    mem_wr(CORE_STATE+96,TASK_HEAD,4);
    mem_wr(TASK_HEAD,TASK_OBJECT,4);
    mem_wr(TASK_OBJECT+16,direct ? 0x12 : 0x13,2);
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
