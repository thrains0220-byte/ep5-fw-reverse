/* SPDX-License-Identifier: GPL-3.0-or-later
 * Original E-P5 descriptor reader; log sinks modeled, descriptor read-only. */
#include "emu.h"

#define BASE 0x7e101020u
#define IMAGE_BYTES 15728576u
#define STACK 0x10000000u
#define DESC 0x11000000u
#define CALLER (STACK + 0x100u)
#define LOG_HEAD 0x7e40eab4u
#define LOG_VALUE 0x7e40ead0u
#define LOG_REC 0x7e3f0464u
#define CODEC 0x7e3f4884u
#define CONTEXT 0x11000000u
#define ART_GLOBAL 0x605f455cu

static uint8_t *image, stack_ram[65536], descriptor[32];
static uint8_t context[0x4600], art_globals[16];
static uint8_t log_return[8] = {0xdf, 0x20, 16};
static uint8_t rec_return[8] = {0xdf, 0xa0, 12};
static uint8_t codec_return[8] = {0xdf, 0xf0, 16};
static unsigned entries, headers;
static unsigned codec_calls, request_words[10], geometry[4];
static int art_mode;
static int reached_stop;
uint64_t emu_ns;

static int within(uint32_t address, uint32_t length, uint32_t base, uint32_t size)
{
    return address >= base && (uint64_t)address + length <= (uint64_t)base + size;
}

uint8_t *mem_host(uint32_t address, uint32_t length)
{
    if (within(address, length, LOG_HEAD, 8)) return log_return + address - LOG_HEAD;
    if (within(address, length, LOG_VALUE, 8)) return log_return + address - LOG_VALUE;
    if (art_mode && within(address, length, LOG_REC, 8)) return rec_return + address - LOG_REC;
    if (art_mode && within(address, length, CODEC, 8)) return codec_return + address - CODEC;
    if (within(address, length, BASE, IMAGE_BYTES)) return image + address - BASE;
    if (within(address, length, STACK, sizeof stack_ram)) return stack_ram + address - STACK;
    if (art_mode && within(address, length, CONTEXT, sizeof context)) return context + address - CONTEXT;
    if (art_mode && within(address, length, ART_GLOBAL, sizeof art_globals)) return art_globals + address - ART_GLOBAL;
    if (!art_mode && within(address, length, DESC, sizeof descriptor)) return descriptor + address - DESC;
    return NULL;
}

uint32_t mem_rd(uint32_t address, int size)
{
    uint8_t *p = mem_host(address, (uint32_t)size);
    if (!p) emu_abort(PC, "unmapped read %08x", address);
    uint32_t v = 0;
    for (int i = 0; i < size; ++i) v |= (uint32_t)p[i] << (i * 8);
    return v;
}

void mem_wr(uint32_t address, uint32_t value, int size)
{
    if (!within(address, (uint32_t)size, STACK, sizeof stack_ram))
        emu_abort(PC, "write outside stack %08x", address);
    for (int i = 0; i < size; ++i) stack_ram[address - STACK + i] = (uint8_t)(value >> (8 * i));
}

void mem_misaligned(uint32_t address, int size, int write_access)
{
    emu_abort(PC, "misaligned access %08x size %d write %d", address, size, write_access);
}

int hle_is_hook(uint32_t address)
{
    return address == CALLER + 7 || address == LOG_HEAD || address == LOG_VALUE ||
           (art_mode && (address == LOG_REC || address == CODEC));
}

int hle_check(cpu_t *cpu)
{
    uint32_t pc = cpu->regs[REG_PC];
    if (pc == CALLER + 7) { reached_stop = emu_stop = 1; return 1; }
    if (art_mode && pc == CODEC) {
        if (cpu->regs[REG_A0] != CONTEXT) emu_abort(pc, "unexpected codec context");
        uint32_t p = cpu->regs[REG_A0 + 1];
        if (!within(p, 40, STACK, sizeof stack_ram)) emu_abort(pc, "invalid codec request");
        for (unsigned i = 0; i < 10; ++i) request_words[i] = mem_rd(p + 4 * i, 4);
        for (unsigned i = 0; i < 4; ++i) geometry[i] = mem_rd(p + 4 + 2 * i, 2);
        ++codec_calls;
        cpu->regs[REG_D0] = 0x1234;
    }
    if (pc == LOG_HEAD) ++headers;
    if (pc == LOG_VALUE) {
        uint32_t p = cpu->regs[REG_A0];
        char label[48];
        unsigned i;
        for (i = 0; i < sizeof label - 1; ++i) {
            unsigned c = mem_rd(p + i, 1);
            if (!c) break;
            if (c < 32 || c > 126 || c == '"' || c == '\\') emu_abort(pc, "invalid label");
            label[i] = (char)c;
        }
        label[i] = 0;
        printf("%s{\"label\":\"%s\",\"value\":%u}", entries ? "," : "", label, cpu->regs[REG_D0]);
        ++entries;
    }
    return 0;
}

void soc_tick(uint64_t cycles) { emu_ns += cycles; }
uint64_t soc_next_event(void) { return emu_ns + 1; }

int main(int argc, char **argv)
{
    if (argc != 2 && argc != 3) return 2;
    if (argc == 3) {
        if (!strcmp(argv[2], "art-full")) art_mode = 1;
        else if (!strcmp(argv[2], "art-small")) art_mode = 2;
        else return 2;
    }
    FILE *f = fopen(argv[1], "rb");
    image = malloc(IMAGE_BYTES);
    if (!f || !image || fread(image, 1, IMAGE_BYTES, f) != IMAGE_BYTES || fgetc(f) != EOF) return 2;
    fclose(f);
    const uint32_t words[] = {0x12345678, 0x87654321};
    for (unsigned i = 0; i < 8; ++i) descriptor[i] = (uint8_t)(words[i / 4] >> (8 * (i % 4)));
    for (unsigned i = 0; i < 10; ++i) {
        descriptor[8 + 2 * i] = (uint8_t)(0x310 + i);
        descriptor[9 + 2 * i] = 3;
    }
    for (unsigned i = 0; i < 4; ++i) descriptor[28 + i] = (uint8_t)(0xabcdef01u >> (8 * i));
    if (art_mode) {
        uint32_t b0 = CONTEXT + 0x100;
        for (unsigned i = 0; i < 4; ++i) {
            context[84 + i] = (uint8_t)(b0 >> (8 * i));
            art_globals[i] = (uint8_t)(0x12000000u >> (8 * i));
        }
        context[0x100 + 17454] = art_mode == 2;
        const uint16_t dimensions[] = {art_mode == 1 ? 4608 : 640, art_mode == 1 ? 3456 : 480};
        for (unsigned i = 0; i < 4; ++i) {
            art_globals[4 + 2 * i] = (uint8_t)dimensions[i % 2];
            art_globals[5 + 2 * i] = (uint8_t)(dimensions[i % 2] >> 8);
        }
    }
    uint8_t *call = stack_ram + 0x100;
    uint32_t displacement = (art_mode ? 0x7e3ed85cu : 0x7e40fba4u) - CALLER;
    call[0] = 0xdd;
    for (unsigned i = 0; i < 4; ++i) call[1 + i] = (uint8_t)(displacement >> (8 * i));
    call[5] = art_mode ? 0xb0 : 0x20; call[6] = art_mode ? 56 : 8; call[7] = 0xcb;
    cpus[0].running = 1;
    cpus[0].irq_level = 7;
    cpus[0].regs[REG_PC] = CALLER;
    cpus[0].regs[REG_SP] = STACK + 0xf000;
    cpus[0].regs[REG_A0] = art_mode ? CONTEXT : DESC;
    const unsigned saved[] = {2, 3, REG_A0 + 2, REG_A0 + 3};
    for (unsigned i = 0; i < 4; ++i) cpus[0].regs[saved[i]] = 0xcafe1000u + i;
    if (!art_mode) printf("{\"fields\":[");
    cpu_run(4000, 0);
    int preserved = cpus[0].regs[REG_SP] == STACK + 0xf000;
    for (unsigned i = 0; i < 4; ++i) preserved &= cpus[0].regs[saved[i]] == 0xcafe1000u + i;
    if (art_mode) {
        printf("{\"buffer_address\":%u,\"geometry_u16\":[%u,%u,%u,%u],\"request_words\":[",
               request_words[0], geometry[0], geometry[1], geometry[2], geometry[3]);
        for (unsigned i = 0; i < 10; ++i) printf("%s%u", i ? "," : "", request_words[i]);
        printf("],\"codec_calls\":%u,\"picture_mode\":%u,\"native_result\":%u,",
               codec_calls, art_mode == 2, cpus[0].regs[REG_D0]);
    } else printf("],");
    printf("\"instructions\":%llu,\"registers_and_stack_preserved\":%s}\n",
           (unsigned long long)cpus[0].icount, preserved ? "true" : "false");
    free(image);
    return reached_stop && preserved && (art_mode ? codec_calls == 1 : headers == 1 && entries == 13) ? 0 : 1;
}
