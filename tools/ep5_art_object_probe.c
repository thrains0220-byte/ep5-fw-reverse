/* Execute stock ART selection events with drawing and logging modeled as sinks. */
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
#define OBJECT (RAM + 0x1000u)
#define AVAILABLE (RAM + 0x2000u)
#define FRAME (RAM + 0xf000u)
#define EVENT 0x7eb29265u
#define DRAW 0x7eb28d11u
#define LOG 0x7eb1a475u
#define DESC 0x7edf7bdcu

static uint8_t *image, ram[RAM_SIZE];
static uint8_t draw_return[8] = {0xdf, 0xf0, 84};
static uint8_t log_return[8] = {0xdf, 0xc0, 12};
static unsigned draw_calls, log_calls, invalid_write, stopped, monitor_writes;
uint64_t emu_ns;

uint8_t *mem_host(uint32_t a, uint32_t n)
{
    if (a >= DRAW && (uint64_t)a + n <= DRAW + sizeof draw_return) return draw_return + a - DRAW;
    if (a >= LOG && (uint64_t)a + n <= LOG + sizeof log_return) return log_return + a - LOG;
    if (a >= BASE && (uint64_t)a + n <= (uint64_t)BASE + SIZE) return image + a - BASE;
    if (a >= RAM && (uint64_t)a + n <= (uint64_t)RAM + RAM_SIZE) return ram + a - RAM;
    return NULL;
}
uint32_t mem_rd(uint32_t a, int n)
{
    uint8_t *p = mem_host(a, n);
    if (!p) emu_abort(PC, "unmapped read %08x", a);
    uint32_t v = 0;
    for (int i = 0; i < n; ++i) v |= (uint32_t)p[i] << (8 * i);
    return v;
}
void mem_wr(uint32_t a, uint32_t v, int n)
{
    if (a < RAM || (uint64_t)a + n > (uint64_t)RAM + RAM_SIZE)
        emu_abort(PC, "unmapped write %08x", a);
    if (monitor_writes && !(a == OBJECT + 416 && n == 2) &&
        !(a >= FRAME - 1024 && (uint64_t)a + n <= FRAME + 20)) ++invalid_write;
    uint8_t *p = mem_host(a, n);
    for (int i = 0; i < n; ++i) p[i] = (uint8_t)(v >> (8 * i));
}
void mem_misaligned(uint32_t a, int n, int w) { emu_abort(PC, "misaligned %08x/%d/%d", a, n, w); }
int hle_is_hook(uint32_t a) { return a == DRAW || a == LOG || a == EVENT || a == 0x7eb2926e || a == 0x7eb292d8 || a == CALLER + 7; }
int hle_check(cpu_t *c)
{
    if (c->regs[REG_PC] == CALLER + 7) { stopped = emu_stop = 1; return 1; }
    if (getenv("EP5_TRACE") && (c->regs[REG_PC] == EVENT || c->regs[REG_PC] == 0x7eb2926e || c->regs[REG_PC] == 0x7eb292d8))
        fprintf(stderr, "pc=%08x sp=%08x mdr=%08x stack=%08x %08x %08x\n", c->regs[REG_PC], c->regs[REG_SP], c->regs[REG_MDR], mem_rd(c->regs[REG_SP],4), mem_rd(c->regs[REG_SP]+4,4), mem_rd(c->regs[REG_SP]+12,4));
    if (c->regs[REG_PC] == DRAW) {
        ++draw_calls;
        if (getenv("EP5_TRACE")) fprintf(stderr, "draw sp=%08x mdr=%08x\n", c->regs[REG_SP], c->regs[REG_MDR]);
        mem_wr(c->regs[REG_SP] + 84, c->regs[REG_MDR], 4);
    }
    if (c->regs[REG_PC] == LOG) {
        ++log_calls;
        if (getenv("EP5_TRACE")) fprintf(stderr, "log sp=%08x mdr=%08x\n", c->regs[REG_SP], c->regs[REG_MDR]);
        mem_wr(c->regs[REG_SP] + 12, c->regs[REG_MDR], 4);
    }
    return 0; /* execute the synthetic ret with the original call frame */
}
void soc_tick(uint64_t cycles) { emu_ns += cycles; }
uint64_t soc_next_event(void) { return emu_ns + 1; }

static int run(unsigned event, unsigned initial, const uint8_t available[13], unsigned expected, unsigned blocked)
{
    memset(cpus, 0, sizeof cpus[0]);
    memset(ram, 0, sizeof ram);
    monitor_writes = 0;
    mem_wr(CALLER, 0xdd, 1); mem_wr(CALLER + 1, EVENT - CALLER, 4);
    /* This small wrapper allocates four bytes itself, so the incoming call
     * has an empty register list and no additional frame. */
    mem_wr(CALLER + 5, 0, 1); mem_wr(CALLER + 6, 0, 1);
    mem_wr(OBJECT + 412, DESC, 4); mem_wr(OBJECT + 416, initial, 2);
    mem_wr(OBJECT + 420, AVAILABLE, 4); mem_wr(OBJECT + 429, blocked, 1);
    for (unsigned i = 0; i < 13; ++i) mem_wr(AVAILABLE + i, available[i], 1);
    invalid_write = draw_calls = log_calls = stopped = emu_stop = 0;
    monitor_writes = 1;
    cpu_t *c = &cpus[0]; c->running = 1; c->irq_level = 7;
    c->regs[REG_PC] = CALLER; c->regs[REG_SP] = FRAME;
    c->regs[REG_A0] = OBJECT; c->regs[REG_D0] = event;
    c->regs[REG_D0 + 2] = 0x12345678; c->regs[REG_D0 + 3] = 0x87654321;
    c->regs[REG_A0 + 2] = 0x13572468; c->regs[REG_A0 + 3] = 0x24681357;
    cpu_run(20000, 0);
    if (!stopped || c->regs[REG_SP] != FRAME || mem_rd(OBJECT + 416, 2) != expected ||
        c->regs[REG_D0 + 2] != 0x12345678 || c->regs[REG_D0 + 3] != 0x87654321 ||
        c->regs[REG_A0 + 2] != 0x13572468 || c->regs[REG_A0 + 3] != 0x24681357 ||
        invalid_write || draw_calls != !blocked || log_calls != !blocked) {
        fprintf(stderr, "event=%u initial=%u got=%u expected=%u pc=%08x sp=%08x stop=%u draw=%u log=%u writes=%u\n",
                event, initial, mem_rd(OBJECT + 416, 2), expected, c->regs[REG_PC], c->regs[REG_SP], stopped, draw_calls, log_calls, invalid_write);
        return 0;
    }
    return 1;
}
int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    FILE *f = fopen(argv[1], "rb"); image = malloc(SIZE);
    if (!f || !image || fread(image, 1, SIZE, f) != SIZE || fgetc(f) != EOF) return 2;
    fclose(f);
    const uint8_t all[13] = {1,1,1,1,1,1,1,1,1,1,1,1,1};
    const uint8_t sparse[13] = {0,1,0,0,1,0,0,0,0,0,0,1,0};
    const uint8_t nonbinary[13] = {0,1,2,0,1,0,0,0,0,0,0,1,0};
    const uint8_t none[13] = {0};
    if (!run(0, 3, all, 2, 0) || !run(1, 3, all, 4, 0) ||
        !run(0, 0, all, 12, 0) || !run(1, 12, all, 0, 0) ||
        !run(0, 4, sparse, 1, 0) || !run(1, 4, sparse, 11, 0) ||
        !run(0, 1, sparse, 11, 0) || !run(1, 11, sparse, 1, 0) ||
        !run(0, 4, sparse, 4, 1) || !run(1, 4, sparse, 4, 1) ||
        !run(1, 1, nonbinary, 2, 0) || !run(0, 4, nonbinary, 2, 0) ||
        !run(1, 4, none, 13, 0) || !run(0, 4, none, 0, 0)) return 1;
    puts("{\"cases\":14,\"original_event_execution\":true,\"nonbinary_availability_selectable\":true,\"all_unavailable_forward_index\":13,\"all_unavailable_backward_index\":0,\"modeled_draw_and_log\":true,\"stack_and_callee_saved_preserved\":true}");
    free(image);
    return 0;
}
