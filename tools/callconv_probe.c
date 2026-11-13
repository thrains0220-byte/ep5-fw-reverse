/* SPDX-License-Identifier: GPL-3.0-or-later
 * Closed-loop MN103 call/ret contract check on the pinned CPU model.
 * Success requires reaching the unique end PC with the exact stack pointer,
 * restored nonvolatile registers and untouched stack sentinels. Merely
 * reaching an entry dump is never a pass. */
#include "emu.h"

#define RAM_BASE 0x20000000u
#define RAM_BYTES 65536u
#define SP0 (RAM_BASE + 0xe000u)
static uint8_t ram[RAM_BYTES];
static uint32_t target_pc, inner_pc, end_pc;
static int reached_target, reached_inner, reached_end;
static uint32_t target_sp, inner_sp, target_mdr;
uint64_t emu_ns;

static int within(uint32_t a, uint32_t n, uint32_t b, uint32_t l)
{ return a >= b && (uint64_t)a + n <= (uint64_t)b + l; }

uint8_t *mem_host(uint32_t a, uint32_t n)
{
    if (within(a, n, RAM_BASE, RAM_BYTES)) return ram + (a - RAM_BASE);
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
    if (!within(a, n, RAM_BASE, RAM_BYTES)) emu_abort(PC, "unmapped write %08x", a);
    uint8_t *p = mem_host(a, n);
    for (int i = 0; i < n; ++i) p[i] = (uint8_t)(v >> (8 * i));
}
void mem_misaligned(uint32_t a, int n, int w) { emu_abort(PC, "misaligned %08x", a); }
void soc_tick(uint64_t c) { emu_ns += c; }
uint64_t soc_next_event(void) { return emu_ns + 1; }

int hle_is_hook(uint32_t a) { return a == target_pc || a == inner_pc || a == end_pc; }
int hle_check(cpu_t *c)
{
    uint32_t pc = c->regs[REG_PC];
    if (pc == target_pc) {
        ++reached_target;
        target_sp = c->regs[REG_SP];
        target_mdr = c->regs[REG_MDR];
    }
    if (pc == inner_pc) {
        ++reached_inner;
        inner_sp = c->regs[REG_SP];
    }
    if (pc == end_pc) { reached_end = emu_stop = 1; return 1; }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 6) return 2;
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 2;
    size_t n = fread(ram, 1, RAM_BYTES, f);
    int trailing = fgetc(f);
    fclose(f);
    if (!n || trailing != EOF) return 2;
    target_pc = RAM_BASE + strtoul(argv[2], 0, 0);
    inner_pc = RAM_BASE + strtoul(argv[3], 0, 0);
    uint32_t resume_pc = RAM_BASE + strtoul(argv[4], 0, 0);
    end_pc = RAM_BASE + strtoul(argv[5], 0, 0);
    /* Stack sentinels above the probe frame. */
    for (uint32_t off = 8; off <= 0x100; off += 4) mem_wr(SP0 + off, 0xfeed0000u | off, 4);
    cpus[0].running = 1;
    cpus[0].irq_level = 7;
    cpus[0].regs[REG_PC] = RAM_BASE;
    cpus[0].regs[REG_SP] = SP0;
    cpus[0].regs[REG_D0 + 2] = 0xaaaa0002;
    cpus[0].regs[REG_D0 + 3] = 0xaaaa0003;
    if (getenv("EP5_TRACE")) trace = 1;
    cpu_run(5000, 0);
    int ok = reached_end && reached_target == 1 && reached_inner == 1 &&
             cpus[0].regs[REG_SP] == SP0 &&
             /* Probe frame is 40 bytes; call stores the return address at the
              * current SP (S-40) and enters the callee at S-40-32. */
             target_sp == SP0 - 40 - 32 && target_mdr == resume_pc &&
             /* target pushed its own 4-byte frame before the nested call. */
             inner_sp == SP0 - 40 - 32 - 4 &&
             /* ret [d2,d3],32 restored the registers saved by the caller. */
             cpus[0].regs[REG_D0 + 2] == 0x55555555u &&
             cpus[0].regs[REG_D0 + 3] == 0x66666666u &&
             /* The probe reloads its own frame values after the call. The
              * frame lives at SP0-40..SP0-1; (40,sp) aliases the return slot
              * and legitimately holds the return address afterwards. */
             mem_rd(SP0 - 40, 4) == resume_pc && mem_rd(SP0 - 36, 4) == 0x22222222u &&
             mem_rd(SP0 - 32, 4) == 0x12345678u && mem_rd(SP0 - 28, 4) == 0x9abcdef0u &&
             mem_rd(SP0 - 4, 4) == 0x33333333u && mem_rd(SP0, 4) == 0x44444444u &&
             cpus[0].regs[REG_D0] == 0x12345678u && cpus[0].regs[REG_D0 + 1] == 0x22222222u &&
             cpus[0].regs[REG_A0] == 0x33333333u && cpus[0].regs[REG_A0 + 1] == 0x9abcdef0u;
    for (uint32_t off = 8; off <= 0x100; off += 4)
        ok &= mem_rd(SP0 + off, 4) == (0xfeed0000u | off);
    if (!ok) {
        fprintf(stderr, "target_sp=%x (want %x) target_mdr=%x (want %x) inner_sp=%x (want %x)\n",
                target_sp, SP0 - 72, target_mdr, resume_pc, inner_sp, SP0 - 76);
        fprintf(stderr, "d0=%x d1=%x a0=%x a1=%x\n", cpus[0].regs[REG_D0], cpus[0].regs[REG_D0 + 1],
                cpus[0].regs[REG_A0], cpus[0].regs[REG_A0 + 1]);
        for (uint32_t off = 0; off <= 44; off += 4)
            fprintf(stderr, " [%d]=%x", (int)off - 40, mem_rd(SP0 - 40 + off, 4));
        fprintf(stderr, "\n");
    }
    printf("{\"end\":%d,\"target_entries\":%d,\"inner_entries\":%d,\"sp\":\"0x%x\","
           "\"d2\":\"0x%x\",\"d3\":\"0x%x\",\"instructions\":%llu}\n",
           reached_end, reached_target, reached_inner, cpus[0].regs[REG_SP],
           cpus[0].regs[REG_D0 + 2], cpus[0].regs[REG_D0 + 3],
           (unsigned long long)cpus[0].icount);
    return ok ? 0 : 1;
}
