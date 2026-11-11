/* SPDX-License-Identifier: GPL-3.0-or-later
 * Execute original ART code, a cave overlay and compiled colour instructions.
 * Only stack/pixels are writable. Logger/codec are the only service models. */
#include "emu.h"

#define BASE 0x7e101020u
#define IMAGE_BYTES 15728576u
#define CAVE 0x7e128010u
#define CAVE_BYTES 32752u
#define HOOK 0x7e3ed8d1u
#define STACK 0x10000000u
#define CALLER (STACK + 0x100u)
#define CONTEXT 0x11000000u
#define PIXELS 0x12000000u
#define ART_GLOBAL 0x605f455cu
#define CODEC 0x7e3f4884u
#define LOGGER 0x7e3f0464u

static uint8_t *image, stack_ram[65536], context[0x4600], globals[16], pixels[65536];
static uint8_t rec_return[8] = {0xdf, 0xa0, 12}, codec_return[8] = {0xdf, 0xf0, 16};
static uint32_t pixel_bytes, registers_at_hook[8], mdr_at_hook, sp_at_hook, request[10];
static unsigned hook_count, codec_calls;
static uint32_t bridge_call;
static unsigned bridge_count;
static int reached_stop, arguments_preserved = 1;
uint64_t emu_ns;

static int within(uint32_t address, uint32_t size, uint32_t base, uint32_t length)
{
    return address >= base && (uint64_t)address + size <= (uint64_t)base + length;
}

uint8_t *mem_host(uint32_t address, uint32_t size)
{
    if (within(address, size, LOGGER, 8)) return rec_return + (address - LOGGER);
    if (within(address, size, CODEC, 8)) return codec_return + (address - CODEC);
    if (within(address, size, BASE, IMAGE_BYTES)) return image + (address - BASE);
    if (within(address, size, STACK, sizeof stack_ram)) return stack_ram + (address - STACK);
    if (within(address, size, CONTEXT, sizeof context)) return context + (address - CONTEXT);
    if (within(address, size, ART_GLOBAL, sizeof globals)) return globals + (address - ART_GLOBAL);
    if (within(address, size, PIXELS, pixel_bytes)) return pixels + (address - PIXELS);
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
        !within(address, (uint32_t)size, PIXELS, pixel_bytes))
        emu_abort(PC, "write outside stack/pixels %08x", address);
    uint8_t *p = mem_host(address, (uint32_t)size);
    for (int i = 0; i < size; ++i) p[i] = (uint8_t)(value >> (8 * i));
}

void mem_misaligned(uint32_t address, int size, int write_access)
{
    emu_abort(PC, "misaligned access %08x size %d write %d", address, size, write_access);
}

int hle_is_hook(uint32_t address)
{
    return address == HOOK || address == bridge_call || address == CODEC || address == LOGGER || address == CALLER + 7;
}

int hle_check(cpu_t *cpu)
{
    uint32_t pc = cpu->regs[REG_PC];
    if (pc == CALLER + 7) { reached_stop = emu_stop = 1; return 1; }
    if (pc == HOOK) {
        for (unsigned i = 0; i < 8; ++i) registers_at_hook[i] = cpu->regs[i];
        mdr_at_hook = cpu->regs[REG_MDR];
        sp_at_hook = cpu->regs[REG_SP];
        uint32_t p = cpu->regs[REG_A0 + 1];
        if (!within(p, 40, STACK, sizeof stack_ram)) emu_abort(pc, "invalid original request");
        for (unsigned i = 0; i < 10; ++i) request[i] = mem_rd(p + 4 * i, 4);
        ++hook_count;
    }
    if (pc == bridge_call || pc == CODEC) {
        if (hook_count != 1) emu_abort(pc, "native codec without unique entry");
        for (unsigned i = 0; i < 8; ++i) {
            if (registers_at_hook[i] != cpu->regs[i])
                fprintf(stderr, "codec register %u changed: %x -> %x\n", i, registers_at_hook[i], cpu->regs[i]);
            arguments_preserved &= registers_at_hook[i] == cpu->regs[i];
        }
        uint32_t expected_mdr = pc == bridge_call ? mdr_at_hook : bridge_call + 7;
        uint32_t expected_sp = pc == bridge_call ? sp_at_hook : sp_at_hook - 16;
        if (expected_mdr != cpu->regs[REG_MDR] || expected_sp != cpu->regs[REG_SP])
            fprintf(stderr, "codec MDR/SP: %x/%x -> %x/%x\n", mdr_at_hook, sp_at_hook,
                    cpu->regs[REG_MDR], cpu->regs[REG_SP]);
        arguments_preserved &= expected_mdr == cpu->regs[REG_MDR] && expected_sp == cpu->regs[REG_SP];
        uint32_t p = cpu->regs[REG_A0 + 1];
        for (unsigned i = 0; i < 10; ++i) arguments_preserved &= request[i] == mem_rd(p + 4 * i, 4);
        if (pc == CODEC) {
            ++codec_calls;
            cpu->regs[REG_D0] = 0x1234;
        } else ++bridge_count;
    }
    return 0;
}

void soc_tick(uint64_t cycles) { emu_ns += cycles; }
uint64_t soc_next_event(void) { return emu_ns + 1; }

static size_t load(const char *name, uint8_t *p, size_t capacity)
{
    FILE *f = fopen(name, "rb");
    if (!f) { perror(name); exit(2); }
    size_t count = fread(p, 1, capacity, f);
    if (ferror(f) || fgetc(f) != EOF) { fprintf(stderr, "input exceeds bounds\n"); exit(2); }
    fclose(f);
    return count;
}

static uint32_t word(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static void put(uint8_t *p, uint32_t v)
{
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(v >> (8 * i));
}

int main(int argc, char **argv)
{
    if (argc != 8) return 2;
    uint8_t config[40], payload[CAVE_BYTES];
    image = malloc(IMAGE_BYTES);
    if (!image || load(argv[1], image, IMAGE_BYTES) != IMAGE_BYTES || load(argv[3], config, 40) != 40) return 2;
    size_t payload_bytes = load(argv[2], payload, CAVE_BYTES);
    char *tail;
    unsigned long control_offset = strtoul(argv[6], &tail, 10);
    if (*tail || !payload_bytes || payload_bytes < 24 || control_offset > payload_bytes - 24 || (control_offset & 3)) return 2;
    unsigned long call_offset = strtoul(argv[7], &tail, 10);
    if (*tail || call_offset > payload_bytes - 7 || payload[call_offset] != 0xdd ||
        payload[call_offset + 5] != 0xf0 || payload[call_offset + 6] != 16) return 2;
    bridge_call = CAVE + (uint32_t)call_offset;
    const uint8_t expected[] = {0xcd, 0xb3, 0x6f, 0xf0, 0x10};
    if (memcmp(image + (HOOK - BASE), expected, 5)) return 2;
    for (unsigned i = 0; i < CAVE_BYTES; ++i) if (image[CAVE - BASE + i] != 255) return 2;
    memcpy(payload + control_offset, config, 24);
    memcpy(image + (CAVE - BASE), payload, payload_bytes);
    image[HOOK - BASE] = 0xdc;
    put(image + (HOOK - BASE) + 1, CAVE - HOOK);
    pixel_bytes = (uint32_t)load(argv[4], pixels, sizeof pixels);
    if (!pixel_bytes) return 2;
    put(context + 84, CONTEXT + 0x100);
    context[0x100 + 17454] = (uint8_t)word(config + 32);
    put(globals, word(config + 36));
    memcpy(globals + 4, config + 24, 8);
    uint8_t *caller = stack_ram + CALLER - STACK;
    caller[0] = 0xdd;
    put(caller + 1, 0x7e3ed85cu - CALLER);
    caller[5] = 0xb0; caller[6] = 56; caller[7] = 0xcb;
    cpus[0].running = 1;
    cpus[0].irq_level = 7;
    cpus[0].regs[REG_PC] = CALLER;
    cpus[0].regs[REG_SP] = STACK + 0xf000;
    cpus[0].regs[REG_MDR] = 0x13579bdf;
    for (unsigned i = 0; i < 8; ++i) cpus[0].regs[i] = 0xabcd1000u + i;
    cpus[0].regs[REG_A0] = CONTEXT;
    const unsigned saved[] = {2, 3, REG_A0 + 2, REG_A0 + 3};
    cpu_run(50000000, 0);
    int preserved = cpus[0].regs[REG_SP] == STACK + 0xf000;
    for (unsigned i = 0; i < 4; ++i) preserved &= cpus[0].regs[saved[i]] == 0xabcd1000u + saved[i];
    if (!reached_stop || !preserved || !arguments_preserved || codec_calls != 1 || bridge_count != 1 || cpus[0].regs[REG_D0] != 0x1234) {
        fprintf(stderr, "native handoff failed: stop=%d preserved=%d arguments=%d hooks=%u codec=%u result=%x sp=%x\n",
                reached_stop, preserved, arguments_preserved, hook_count, codec_calls,
                cpus[0].regs[REG_D0], cpus[0].regs[REG_SP]);
        return 1;
    }
    FILE *out = fopen(argv[5], "wb");
    if (!out || fwrite(pixels, 1, pixel_bytes, out) != pixel_bytes || fclose(out)) return 2;
    printf("{\"codec_calls\":%u,\"native_result\":%u,\"native_arguments_preserved\":true,"
           "\"registers_and_stack_preserved\":true,\"instructions\":%llu}\n",
           codec_calls, cpus[0].regs[REG_D0], (unsigned long long)cpus[0].icount);
    free(image);
    return 0;
}
