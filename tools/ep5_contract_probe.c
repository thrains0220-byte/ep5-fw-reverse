/* SPDX-License-Identifier: GPL-3.0-or-later
 * Stock producer/boot contracts. Allocator/logs modeled; no ISP or device I/O. */
#include "emu.h"

#define BASE 0x7e101020u
#define IMAGE_BYTES 15728576u
#define STACK 0x10000000u
#define CALLER (STACK + 0x100u)
#define RAM 0x605f4000u
#define PACKET 0x605f4510u
#define TASK 0x605f57e4u
#define MESSAGE (STACK + 0x200u)
#define WRAPPER (STACK + 0x220u)
#define BOOT_GLOBAL 0x605112d0u

static uint8_t *image, stack_ram[65536], ram[0x4000], boot_globals[16];
static const struct service { uint32_t pc; uint8_t ret[8]; } services[] = {
    {0x7e3fd443, {0xdf, 0x00, 4}}, /* log */
    {0x7e3fd45c, {0xdf, 0x20, 8}}, /* log with value */
    {0x7e3fd94a, {0xdf, 0x00, 0}}, /* trace mark */
    {0x7e3fd922, {0xdf, 0x80, 4}}, /* trace sink */
    {0x7e23e0a2, {0xdf, 0x00, 4}}, /* allocator only */
    {0x7e106f3f, {0xdf, 0xf0, 44}}, /* error sink */
    {0x7e3f0464, {0xdf, 0xa0, 12}}, /* REC log */
    {0x7e3f4884, {0xdf, 0xf0, 16}}, /* codec request sink, no encoding */
};
static int mode, stopped, allocation_failed;
static unsigned allocation_calls, allocation_bytes, allocation_flags, errors;
static unsigned boot_source, boot_destination, boot_bytes;
static unsigned codec_calls, jpeg_buffer, jpeg_geometry[4];
uint64_t emu_ns;

static int within(uint32_t a, uint32_t n, uint32_t base, uint32_t bytes)
{
    return a >= base && (uint64_t)a + n <= (uint64_t)base + bytes;
}

uint8_t *mem_host(uint32_t a, uint32_t n)
{
    for (unsigned i = 0; i < sizeof services / sizeof *services; ++i)
        if (within(a, n, services[i].pc, 8))
            return (uint8_t *)services[i].ret + (a - services[i].pc);
    if (within(a, n, BASE, IMAGE_BYTES)) return image + (a - BASE);
    if (within(a, n, STACK, sizeof stack_ram)) return stack_ram + (a - STACK);
    if (within(a, n, RAM, sizeof ram)) return ram + (a - RAM);
    if (within(a, n, BOOT_GLOBAL, sizeof boot_globals)) return boot_globals + (a - BOOT_GLOBAL);
    return NULL;
}

uint32_t mem_rd(uint32_t a, int n)
{
    uint8_t *p = mem_host(a, (uint32_t)n);
    if (!p) emu_abort(PC, "unmapped read %08x", a);
    uint32_t v = 0;
    for (int i = 0; i < n; ++i) v |= (uint32_t)p[i] << (8 * i);
    return v;
}

void mem_wr(uint32_t a, uint32_t v, int n)
{
    if (!within(a, (uint32_t)n, STACK, sizeof stack_ram) &&
        !within(a, (uint32_t)n, PACKET, 396) &&
        !within(a, (uint32_t)n, TASK, 676) &&
        !within(a, (uint32_t)n, BOOT_GLOBAL, sizeof boot_globals))
        emu_abort(PC, "write outside permitted state %08x", a);
    uint8_t *p = mem_host(a, (uint32_t)n);
    for (int i = 0; i < n; ++i) p[i] = (uint8_t)(v >> (8 * i));
}

void mem_misaligned(uint32_t a, int n, int write_access)
{
    emu_abort(PC, "misaligned %08x size %d write %d", a, n, write_access);
}

int hle_is_hook(uint32_t a)
{
    if (a == CALLER + 7 || (mode == 0 && a == 0x7e10187b)) return 1;
    for (unsigned i = 0; i < sizeof services / sizeof *services; ++i)
        if (a == services[i].pc) return 1;
    return 0;
}

int hle_check(cpu_t *cpu)
{
    uint32_t pc = cpu->regs[REG_PC];
    if (pc == CALLER + 7) { stopped = emu_stop = 1; return 1; }
    if (mode == 0 && pc == 0x7e10187b) {
        boot_source = cpu->regs[REG_A0];
        boot_destination = cpu->regs[REG_A0 + 1];
        boot_bytes = cpu->regs[REG_D0 + 1];
        stopped = emu_stop = 1;
        return 1;
    }
    if (pc == 0x7e23e0a2) {
        ++allocation_calls;
        allocation_bytes = cpu->regs[REG_D0];
        allocation_flags = cpu->regs[REG_D0 + 1];
        cpu->regs[REG_D0] = allocation_failed ? 0 : 0x12000000;
    }
    if (pc == 0x7e106f3f) ++errors;
    if (pc == 0x7e3f4884) {
        uint32_t request = cpu->regs[REG_A0 + 1];
        if (cpu->regs[REG_A0] != STACK + 0x3000 || !within(request, 40, STACK, sizeof stack_ram))
            emu_abort(pc, "unexpected JPEG context/request");
        jpeg_buffer = mem_rd(request, 4);
        for (unsigned i = 0; i < 4; ++i) jpeg_geometry[i] = mem_rd(request + 4 + 2 * i, 2);
        ++codec_calls;
        cpu->regs[REG_D0] = 0x1234;
    }
    return 0;
}

void soc_tick(uint64_t cycles) { emu_ns += cycles; }
uint64_t soc_next_event(void) { return emu_ns + 1; }

static void put(uint32_t a, uint32_t v, int n) { mem_wr(a, v, n); }

int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    const char *name = argv[2];
    if (!strcmp(name, "boot")) mode = 0;
    else if (!strcmp(name, "neutral") || !strcmp(name, "pinhole")) mode = 2;
    else if (!strcmp(name, "allocate") || !strcmp(name, "existing") ||
             !strcmp(name, "failed") || !strcmp(name, "cropped")) mode = 1;
    else return 2;
    FILE *f = fopen(argv[1], "rb");
    image = malloc(IMAGE_BYTES);
    if (!f || !image || fread(image, 1, IMAGE_BYTES, f) != IMAGE_BYTES || fgetc(f) != EOF) return 2;
    fclose(f);
    uint32_t entry = mode == 0 ? 0x7e1011b0 : mode == 1 ? 0x7e40a20b : 0x7e40b368;
    uint32_t displacement = entry - CALLER;
    stack_ram[0x100] = 0xdd;
    for (unsigned i = 0; i < 4; ++i) stack_ram[0x101 + i] = (uint8_t)(displacement >> (8 * i));
    stack_ram[0x105] = mode == 2 ? 0xf0 : 0;
    stack_ram[0x106] = mode == 2 ? 36 : 0;
    stack_ram[0x107] = 0xcb;
    put(PACKET, 1, 2); put(PACKET + 2, 3, 2);
    put(PACKET + 6, !strcmp(name, "pinhole") ? 73 : 0, 2);
    put(PACKET + 96, !strcmp(name, "cropped") ? 2 : 1, 1); /* native aspect index */
    put(WRAPPER + 8, PACKET, 4);
    put(MESSAGE, 3, 4); put(MESSAGE + 4, 0x12345678, 4); put(MESSAGE + 12, PACKET, 4);
    if (!strcmp(name, "existing")) put(PACKET + 76, 0x12001000, 4);
    allocation_failed = !strcmp(name, "failed");
    cpus[0].running = 1;
    cpus[0].irq_level = 7;
    cpus[0].regs[REG_PC] = mode == 0 ? entry : CALLER;
    cpus[0].regs[REG_SP] = STACK + 0xf000;
    cpus[0].regs[REG_A0] = mode == 1 ? WRAPPER : MESSAGE;
    cpus[0].regs[REG_A0 + 1] = PACKET;
    cpus[0].regs[REG_D0] = TASK;
    const unsigned saved[] = {2, 3, REG_A0 + 2, REG_A0 + 3};
    for (unsigned i = 0; i < 4; ++i) cpus[0].regs[saved[i]] = 0xcafe1000u + i;
    cpu_run(20000, 0);
    int preserved = cpus[0].regs[REG_SP] == STACK + 0xf000;
    int jpeg_ok = 1;
    for (unsigned i = 0; i < 4; ++i) preserved &= cpus[0].regs[saved[i]] == 0xcafe1000u + i;
    if (mode == 0) {
        printf("{\"source\":%u,\"destination\":%u,\"bytes\":%u}", boot_source, boot_destination, boot_bytes);
    } else if (mode == 1) {
        unsigned result = cpus[0].regs[REG_D0];
        unsigned long long instructions = cpus[0].icount;
        int jpeg_preserved = 0;
        if (stopped && preserved && result == 0) {
            put(STACK + 0x3000 + 84, STACK + 0x3100, 4);
            displacement = 0x7e3ed85c - CALLER;
            for (unsigned i = 0; i < 4; ++i) stack_ram[0x101 + i] = (uint8_t)(displacement >> (8 * i));
            stack_ram[0x105] = 0xb0; stack_ram[0x106] = 56;
            cpus[0].regs[REG_A0] = STACK + 0x3000;
            cpus[0].regs[REG_PC] = CALLER;
            emu_stop = stopped = 0;
            cpu_run(20000, 0);
            jpeg_preserved = stopped && cpus[0].regs[REG_SP] == STACK + 0xf000 &&
                             cpus[0].regs[REG_D0] == 0x1234;
            for (unsigned i = 0; i < 4; ++i)
                jpeg_preserved &= cpus[0].regs[saved[i]] == 0xcafe1000u + i;
            jpeg_ok = jpeg_preserved;
        }
        printf("{\"buffer\":%u,\"allocation_calls\":%u,\"allocation_bytes\":%u,\"allocation_flags\":%u,\"errors\":%u,\"geometry_u16\":[",
               mem_rd(PACKET + 76, 4), allocation_calls, allocation_bytes, allocation_flags, errors);
        for (unsigned i = 0; i < 6; ++i) printf("%s%u", i ? "," : "", mem_rd(PACKET + 80 + 2 * i, 2));
        printf("],\"result\":%u,\"instructions\":%llu,\"registers_and_stack_preserved\":%s,"
               "\"codec_calls\":%u,\"jpeg_buffer\":%u,\"jpeg_geometry_u16\":[%u,%u,%u,%u],\"jpeg_frame_preserved\":%s}",
               result, instructions, preserved ? "true" : "false", codec_calls, jpeg_buffer,
               jpeg_geometry[0], jpeg_geometry[1], jpeg_geometry[2], jpeg_geometry[3], jpeg_preserved ? "true" : "false");
    } else {
        printf("{\"initializer\":%u,\"functions\":[", mem_rd(TASK + 4, 4));
        unsigned count = 0;
        for (unsigned i = 0; i < 4; ++i) {
            uint32_t func = mem_rd(TASK + 4 + 52 + 8 * i + 4, 4);
            if (func) printf("%s%u", count++ ? "," : "", func);
        }
        printf("],\"result\":%u,\"instructions\":%llu,\"registers_and_stack_preserved\":%s}",
               cpus[0].regs[REG_D0], (unsigned long long)cpus[0].icount, preserved ? "true" : "false");
    }
    puts(""); free(image);
    return stopped && (mode == 0 || preserved) && jpeg_ok ? 0 : 1;
}
