#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "emu.h"

#define IMAGE_BASE 0x7e101020u
#define IMAGE_SIZE 15728576u
#define STACK_BASE 0x10000000u
#define STACK_SIZE 65536u
#define CALLER (STACK_BASE + 0x100u)
#define OBJECT (STACK_BASE + 0x1000u)
#define FRAME (STACK_BASE + 0xf000u)
#define DESCRIPTORS 0x7ed882b4u
#define EVENT_TABLE 0x7edbfa90u
#define LOOKUP 0x7eab789fu
#define DISPATCH 0x7eab775cu

static uint8_t *image;
static uint8_t stack_ram[STACK_SIZE];
static int stopped;
static uint32_t expected_callback;
uint64_t emu_ns;

uint8_t *mem_host(uint32_t address, uint32_t length)
{
    if (address >= IMAGE_BASE && (uint64_t)address + length <= (uint64_t)IMAGE_BASE + IMAGE_SIZE)
        return image + address - IMAGE_BASE;
    if (address >= STACK_BASE && (uint64_t)address + length <= (uint64_t)STACK_BASE + STACK_SIZE)
        return stack_ram + address - STACK_BASE;
    return NULL;
}

uint32_t mem_rd(uint32_t address, int size)
{
    uint8_t *memory = mem_host(address, (uint32_t)size);
    if (!memory) emu_abort(PC, "unmapped read %08x", address);
    uint32_t result = 0;
    for (int index = 0; index < size; ++index) result |= (uint32_t)memory[index] << (8 * index);
    return result;
}

void mem_wr(uint32_t address, uint32_t value, int size)
{
    if (address < STACK_BASE || (uint64_t)address + size > (uint64_t)STACK_BASE + STACK_SIZE)
        emu_abort(PC, "write outside modeled stack %08x", address);
    uint8_t *memory = mem_host(address, (uint32_t)size);
    for (int index = 0; index < size; ++index) memory[index] = (uint8_t)(value >> (8 * index));
}

void mem_misaligned(uint32_t address, int size, int write_access)
{ emu_abort(PC, "misaligned %08x size %d write %d", address, size, write_access); }
int hle_is_hook(uint32_t address) { return address == CALLER + 7 || address == expected_callback; }
int hle_check(cpu_t *cpu)
{
    if (cpu->regs[REG_PC] == CALLER + 7 || cpu->regs[REG_PC] == expected_callback) {
        stopped = emu_stop = 1;
        return 1;
    }
    return 0;
}
void soc_tick(uint64_t cycles) { emu_ns += cycles; }
uint64_t soc_next_event(void) { return emu_ns + 1; }

static int invoke(uint32_t event, uint32_t expected)
{
    expected_callback = 0;
    memset(cpus, 0, sizeof(cpus[0]));
    memset(stack_ram, 0, sizeof stack_ram);
    uint32_t displacement = LOOKUP - CALLER;
    mem_wr(CALLER, 0xdd, 1);
    mem_wr(CALLER + 1, displacement, 4);
    mem_wr(CALLER + 5, 0xf0, 1);
    mem_wr(CALLER + 6, 20, 1);
    mem_wr(OBJECT, 3, 1);
    mem_wr(OBJECT + 4, DESCRIPTORS, 4);
    cpu_t *cpu = &cpus[0];
    cpu->running = 1;
    cpu->irq_level = 7;
    cpu->regs[REG_PC] = CALLER;
    cpu->regs[REG_SP] = FRAME;
    cpu->regs[REG_A0] = OBJECT;
    cpu->regs[REG_D0] = event;
    cpu->regs[REG_D0 + 2] = 0x12345678;
    cpu->regs[REG_D0 + 3] = 0x87654321;
    cpu->regs[REG_A0 + 2] = 0x13572468;
    cpu->regs[REG_A0 + 3] = 0x24681357;
    stopped = emu_stop = 0;
    cpu_run(20000, 0);
    if (!stopped || cpu->regs[REG_SP] != FRAME || cpu->regs[REG_D0] != expected ||
        cpu->regs[REG_D0 + 2] != 0x12345678 || cpu->regs[REG_D0 + 3] != 0x87654321 ||
        cpu->regs[REG_A0 + 2] != 0x13572468 || cpu->regs[REG_A0 + 3] != 0x24681357) {
        fprintf(stderr, "event %08x returned %08x expected %08x stop=%d sp=%08x\n",
                event, cpu->regs[REG_D0], expected, stopped, cpu->regs[REG_SP]);
        return 0;
    }
    return 1;
}

static int dispatch(uint32_t event, uint32_t callback)
{
    memset(cpus, 0, sizeof(cpus[0]));
    memset(stack_ram, 0, sizeof stack_ram);
    expected_callback = callback;
    mem_wr(CALLER, 0xdd, 1);
    mem_wr(CALLER + 1, DISPATCH - CALLER, 4);
    mem_wr(CALLER + 5, 0xf0, 1);
    mem_wr(CALLER + 6, 48, 1);
    mem_wr(OBJECT, 3, 1);
    mem_wr(OBJECT + 1, 5, 1);
    mem_wr(OBJECT + 4, DESCRIPTORS, 4);
    cpu_t *cpu = &cpus[0];
    cpu->running = 1;
    cpu->irq_level = 7;
    cpu->regs[REG_PC] = CALLER;
    cpu->regs[REG_SP] = FRAME;
    cpu->regs[REG_A0] = OBJECT;
    cpu->regs[REG_D0] = event;
    stopped = emu_stop = 0;
    cpu_run(20000, 0);
    if (!stopped || cpu->regs[REG_PC] != callback || cpu->regs[REG_A0] != OBJECT ||
        cpu->regs[REG_D0] != event) {
        fprintf(stderr, "dispatch %08x reached %08x expected %08x stop=%d\n",
                event, cpu->regs[REG_PC], callback, stopped);
        return 0;
    }
    return 1;
}

static int dispatch_noop(uint32_t event)
{
    memset(cpus, 0, sizeof(cpus[0]));
    memset(stack_ram, 0, sizeof stack_ram);
    expected_callback = 0;
    mem_wr(CALLER, 0xdd, 1);
    mem_wr(CALLER + 1, DISPATCH - CALLER, 4);
    mem_wr(CALLER + 5, 0xf0, 1);
    mem_wr(CALLER + 6, 48, 1);
    mem_wr(OBJECT, 3, 1);
    mem_wr(OBJECT + 1, 5, 1);
    mem_wr(OBJECT + 4, DESCRIPTORS, 4);
    cpu_t *cpu = &cpus[0];
    cpu->running = 1;
    cpu->irq_level = 7;
    cpu->regs[REG_PC] = CALLER;
    cpu->regs[REG_SP] = FRAME;
    cpu->regs[REG_A0] = OBJECT;
    cpu->regs[REG_D0] = event;
    cpu->regs[REG_D0 + 2] = 0x12345678;
    cpu->regs[REG_D0 + 3] = 0x87654321;
    cpu->regs[REG_A0 + 2] = 0x13572468;
    cpu->regs[REG_A0 + 3] = 0x24681357;
    stopped = emu_stop = 0;
    cpu_run(20000, 0);
    if (!stopped || cpu->regs[REG_PC] != CALLER + 7 || cpu->regs[REG_SP] != FRAME ||
        cpu->regs[REG_D0] != 0 || mem_rd(OBJECT, 1) != 3 || mem_rd(OBJECT + 1, 1) != 5 ||
        mem_rd(OBJECT + 8, 2) != 0xffff || cpu->regs[REG_D0 + 2] != 0x12345678 ||
        cpu->regs[REG_D0 + 3] != 0x87654321 || cpu->regs[REG_A0 + 2] != 0x13572468 ||
        cpu->regs[REG_A0 + 3] != 0x24681357) {
        fprintf(stderr, "noop %08x failed pc=%08x sp=%08x\n", event, cpu->regs[REG_PC], cpu->regs[REG_SP]);
        return 0;
    }
    return 1;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    FILE *file = fopen(argv[1], "rb");
    image = malloc(IMAGE_SIZE);
    if (!file || !image || fread(image, 1, IMAGE_SIZE, file) != IMAGE_SIZE || fgetc(file) != EOF)
        return 2;
    fclose(file);
    for (unsigned index = 0; index < 64; ++index) {
        uint32_t event = mem_rd(EVENT_TABLE + index * 8, 4);
        uint32_t row = mem_rd(EVENT_TABLE + index * 8 + 4, 4);
        if (row != index || !invoke(event, row)) return 1;
    }
    if (!invoke(0xffffffffu, 0x0000ffffu)) return 1;
    if (!dispatch(0x9031u, 0x7eaf1fa3u) || !dispatch(0x9032u, 0x7eaf2fb3u)) return 1;
    printf("{\"events\":64,\"unknown_rejected\":true,\"stack_and_registers_preserved\":true,"
           "\"art_dial_callbacks_selected\":2}\n");
    free(image);
    return 0;
}
