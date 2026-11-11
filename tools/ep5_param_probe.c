/* SPDX-License-Identifier: GPL-3.0-or-later
 * One stock ART send call, one cave veneer, one modeled send sink. No ISP. */
#include "emu.h"

#define BASE 0x7e101020u
#define IMAGE_BYTES 15728576u
#define CAVE 0x7e128010u
#define CAVE_BYTES 32752u
#define HOOK 0x7e3ed835u
#define CONTINUE 0x7e3ed83cu
#define SEND 0x7e3fca97u
#define PACKET 0x605f4510u
#define CONTEXT 0x11000000u
#define SETTINGS 0x12000000u
#define STACK 0x60000000u

static uint8_t *image, packet[396], context[128], settings[18200], stack_ram[65536];
static uint8_t send_return[8] = {0xdf, 0xa0, 20};
static uint32_t initial[8], initial_sp, original_contrast, param_call;
static int send_calls, reached_stop, preserved = 1, send_envelope_valid = 1;
static unsigned packet_writes;
static uint32_t contrast_at_send;
uint64_t emu_ns;

static int within(uint32_t address, uint32_t size, uint32_t base, uint32_t length)
{
    return address >= base && (uint64_t)address + size <= (uint64_t)base + length;
}

uint8_t *mem_host(uint32_t address, uint32_t size)
{
    if (within(address, size, SEND, 8)) return send_return + (address - SEND);
    if (within(address, size, BASE, IMAGE_BYTES)) return image + (address - BASE);
    if (within(address, size, PACKET, sizeof packet)) return packet + (address - PACKET);
    if (within(address, size, CONTEXT, sizeof context)) return context + (address - CONTEXT);
    if (within(address, size, SETTINGS, sizeof settings)) return settings + (address - SETTINGS);
    if (within(address, size, STACK, sizeof stack_ram)) return stack_ram + (address - STACK);
    return NULL;
}

uint32_t mem_rd(uint32_t address, int size)
{
    uint8_t *p = mem_host(address, (uint32_t)size);
    if (!p) emu_abort(PC, "unmapped read %08x", address);
    uint32_t value = 0;
    for (int i = 0; i < size; ++i) value |= (uint32_t)p[i] << (8 * i);
    return value;
}

void mem_wr(uint32_t address, uint32_t value, int size)
{
    if (!within(address, (uint32_t)size, STACK, sizeof stack_ram) &&
        !(address == PACKET + 157 && size == 1))
        emu_abort(PC, "write outside stack/contrast %08x", address);
    if (address == PACKET + 157) ++packet_writes;
    uint8_t *p = mem_host(address, (uint32_t)size);
    if (!p) emu_abort(PC, "unmapped write %08x", address);
    for (int i = 0; i < size; ++i) p[i] = (uint8_t)(value >> (8 * i));
}

void mem_misaligned(uint32_t address, int size, int write_access)
{
    emu_abort(PC, "misaligned %08x size %d write %d", address, size, write_access);
}

int hle_is_hook(uint32_t address)
{
    return address == SEND || address == CONTINUE;
}

int hle_check(cpu_t *cpu)
{
    uint32_t pc = cpu->regs[REG_PC];
    if (pc == SEND) {
        ++send_calls;
        for (unsigned i = 0; i < 8; ++i) preserved &= cpu->regs[i] == initial[i];
        preserved &= cpu->regs[REG_SP] == initial_sp - 20 &&
                     cpu->regs[REG_MDR] == param_call + 7;
        send_envelope_valid &= cpu->regs[REG_A0] == initial_sp + 4 &&
            mem_rd(cpu->regs[REG_A0], 4) == 0x123u &&
            mem_rd(cpu->regs[REG_A0] + 4, 4) == 1 &&
            mem_rd(cpu->regs[REG_A0] + 8, 4) == 1 &&
            mem_rd(cpu->regs[REG_A0] + 12, 4) == initial[REG_A0 + 2];
        contrast_at_send = mem_rd(PACKET + 157, 1);
        if (cpu->regs[REG_A0 + 2] != initial[REG_A0 + 2] ||
            cpu->regs[REG_A0 + 3] != CONTEXT)
            emu_abort(pc, "original send arguments changed");
        cpu->regs[REG_D0] = 0x2345;
    }
    if (pc == CONTINUE) {
        reached_stop = emu_stop = 1;
        preserved &= cpu->regs[REG_SP] == initial_sp && cpu->regs[REG_MDR] == CONTINUE;
        for (unsigned i = 1; i < 8; ++i) preserved &= cpu->regs[i] == initial[i];
        preserved &= cpu->regs[REG_D0] == 0x2345;
        return 1;
    }
    return 0;
}

void soc_tick(uint64_t cycles) { emu_ns += cycles; }
uint64_t soc_next_event(void) { return emu_ns + 1; }

static size_t load(const char *name, uint8_t *target, size_t capacity)
{
    FILE *f = fopen(name, "rb");
    if (!f) { perror(name); exit(2); }
    size_t count = fread(target, 1, capacity, f);
    if (ferror(f) || fgetc(f) != EOF) { fprintf(stderr, "input exceeds bounds\n"); exit(2); }
    fclose(f);
    return count;
}

static void put32(uint8_t *target, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) target[i] = (uint8_t)(value >> (8 * i));
}

static void put16(uint8_t *target, uint16_t value)
{
    target[0] = (uint8_t)value;
    target[1] = (uint8_t)(value >> 8);
}

int main(int argc, char **argv)
{
    if (argc != 7) return 2;
    uint8_t payload[CAVE_BYTES];
    image = malloc(IMAGE_BYTES);
    if (!image || load(argv[1], image, IMAGE_BYTES) != IMAGE_BYTES) return 2;
    size_t count = load(argv[2], payload, sizeof payload);
    char *tail;
    unsigned long control = strtoul(argv[3], &tail, 10);
    if (*tail || count < 24 || control > count - 24 || (control & 3)) return 2;
    unsigned long entry = strtoul(argv[4], &tail, 10);
    if (*tail || entry >= count) return 2;
    unsigned long call = strtoul(argv[5], &tail, 10);
    if (*tail || call > count - 7 || payload[call] != 0xdd ||
        payload[call + 5] != 0xa0 || payload[call + 6] != 20) return 2;
    param_call = CAVE + (uint32_t)call;
    const uint8_t old[] = {0xdd, 0x62, 0xf2, 0, 0, 0xa0, 20};
    if (memcmp(image + HOOK - BASE, old, sizeof old)) return 2;
    memcpy(image + CAVE - BASE, payload, count);
    image[HOOK - BASE] = 0xdc;
    put32(image + HOOK - BASE + 1, CAVE + (uint32_t)entry - HOOK);
    image[HOOK - BASE + 5] = image[HOOK - BASE + 6] = 0xcb;

    const char *name = argv[6];
    if (!strcmp(name, "disabled")) put32(image + CAVE - BASE + control + 4, 0);
    else if (!strcmp(name, "lut_mode")) put32(image + CAVE - BASE + control + 4, 1);
    else if (!strcmp(name, "enabled") || !strcmp(name, "wrong_tag") ||
             !strcmp(name, "wrong_mode") || !strcmp(name, "wrong_variant") ||
             !strcmp(name, "wrong_filter") || !strcmp(name, "wrong_packet") ||
             !strcmp(name, "wrong_settings") || !strcmp(name, "wrong_aspect") ||
             !strcmp(name, "wrong_size_code") || !strcmp(name, "wrong_geometry") ||
             !strcmp(name, "wrong_source") || !strcmp(name, "wrong_value"))
        put32(image + CAVE - BASE + control + 4, 2);
    else return 2;
    if (!strcmp(name, "wrong_tag")) put32(image + CAVE - BASE + control, 0);
    put32(context + 84, !strcmp(name, "wrong_settings") ? 0 : SETTINGS);
    settings[17471] = !strcmp(name, "wrong_mode") ? 104 : 105;
    settings[18147] = !strcmp(name, "wrong_variant") ? 2 : 1;
    put16(settings + 17442, !strcmp(name, "wrong_source") ? 1 : 0);
    put16(packet, 1);
    put16(packet + 2, !strcmp(name, "wrong_size_code") ? 2 : 3);
    put16(packet + 6, !strcmp(name, "wrong_filter") ? 74 : 73);
    packet[96] = !strcmp(name, "wrong_aspect") ? 2 : 1;
    if (!strcmp(name, "wrong_geometry")) put16(packet + 80, 3200);
    uint16_t pre_send_geometry[6];
    for (unsigned i = 0; i < 6; ++i)
        pre_send_geometry[i] = (uint16_t)packet[80 + i * 2] | (uint16_t)packet[81 + i * 2] << 8;
    packet[157] = !strcmp(name, "wrong_value") ? 2 : 0;
    original_contrast = packet[157];
    cpus[0].running = 1;
    cpus[0].irq_level = 7;
    cpus[0].regs[REG_PC] = HOOK;
    cpus[0].regs[REG_SP] = initial_sp = STACK + 0xf000;
    cpus[0].regs[REG_MDR] = 0x13579bdf;
    for (unsigned i = 0; i < 8; ++i) cpus[0].regs[i] = 0xabcd1000u + i;
    cpus[0].regs[REG_D0] = 1;
    cpus[0].regs[REG_A0] = initial_sp + 4;
    cpus[0].regs[REG_A0 + 2] = !strcmp(name, "wrong_packet") ? PACKET + 4 : PACKET;
    cpus[0].regs[REG_A0 + 3] = CONTEXT;
    put32(stack_ram + (initial_sp - STACK) + 4, 0x123);
    put32(stack_ram + (initial_sp - STACK) + 8, 1);
    put32(stack_ram + (initial_sp - STACK) + 12, 1);
    put32(stack_ram + (initial_sp - STACK) + 16, cpus[0].regs[REG_A0 + 2]);
    memcpy(initial, cpus[0].regs, sizeof initial);
    cpu_run(20000, 0);
    if (!reached_stop || !preserved || !send_envelope_valid || send_calls != 1 ||
        contrast_at_send != (!strcmp(name, "enabled") ? 1u : original_contrast) ||
        packet[157] != (!strcmp(name, "enabled") ? 1u : original_contrast)) return 1;
    printf("{\"name\":\"%s\",\"contrast_before\":%u,\"contrast_after\":%u,"
           "\"native_result\":%u,\"original_send_called_once\":true,"
           "\"registers_and_stack_preserved\":true,\"mdr_at_continue\":%u,"
           "\"packet_writes\":%u,\"send_envelope_valid\":true,"
           "\"contrast_at_send\":%u,\"pre_send_geometry\":[%u,%u,%u,%u,%u,%u],"
           "\"instructions\":%llu}\n",
           name, original_contrast, packet[157], cpus[0].regs[REG_D0],
           cpus[0].regs[REG_MDR], packet_writes, contrast_at_send,
           pre_send_geometry[0], pre_send_geometry[1], pre_send_geometry[2],
           pre_send_geometry[3], pre_send_geometry[4], pre_send_geometry[5],
           (unsigned long long)cpus[0].icount);
    free(image);
    return 0;
}
