/* SPDX-License-Identifier: GPL-3.0-or-later
 * Bounded E-P5 startup branch probe using cmdada's pinned GNU-derived CPU.
 * Only bounded modeled RAM is writable. Service models are listed in the report.
 */
#include "emu.h"

#define BASE 0x7e101020u
#define IMAGE_BYTES 15728576u
#define STACK 0x10000000u
#define STACK_BYTES 65536u
#define STOP 0x7e1c7fa8u
#define DELAY 0x7e1315fbu
#define GET_PARAM 0x7e141667u
#define WIFI 0x7e1c8228u
#define PARAM_RAM 0x603b9000u
#define PARAM_BYTES 0x14000u
#define RECORDS 0x603c9f28u
#define INDEX 0x603b9f28u
#define CALLER (STACK + 0x100u)

static uint8_t *image;
static uint8_t stack_ram[STACK_BYTES];
static uint8_t parameter_ram[PARAM_BYTES];
static int parameter_value, wifi_requests, reached_stop;
static int csv_mode;
static uint32_t stop_address = STOP;
static unsigned parameter_id, delay_argument;
uint64_t emu_ns;

/* Real MN103 return instructions match each modeled callee's call frame. */
static uint8_t delay_return[8] = {0xdf, 0x80, 8};
static uint8_t parameter_return[8] = {0xdf, 0xc0, 12};
static uint8_t wifi_return[8] = {0xdf, 0, 4};

uint8_t *mem_host(uint32_t address, uint32_t length)
{
    const uint32_t services[] = {DELAY, GET_PARAM, WIFI};
    uint8_t *returns[] = {delay_return, parameter_return, wifi_return};
    for (unsigned i = 0; i < 3; ++i)
        if (!(csv_mode && services[i] == GET_PARAM) && address >= services[i] &&
            (uint64_t)address + length <= (uint64_t)services[i] + 8)
            return returns[i] + address - services[i];
    if (address >= BASE && (uint64_t)address + length <= (uint64_t)BASE + IMAGE_BYTES)
        return image + address - BASE;
    if (address >= STACK && (uint64_t)address + length <= (uint64_t)STACK + STACK_BYTES)
        return stack_ram + address - STACK;
    if (csv_mode && address >= PARAM_RAM &&
        (uint64_t)address + length <= (uint64_t)PARAM_RAM + PARAM_BYTES)
        return parameter_ram + address - PARAM_RAM;
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
    uint8_t *p = NULL;
    if (address >= STACK && (uint64_t)address + size <= (uint64_t)STACK + STACK_BYTES)
        p = stack_ram + address - STACK;
    if (csv_mode && address >= PARAM_RAM && (uint64_t)address + size <= (uint64_t)PARAM_RAM + PARAM_BYTES)
        p = parameter_ram + address - PARAM_RAM;
    if (!p) emu_abort(PC, "write outside modeled RAM %08x", address);
    for (int i = 0; i < size; ++i) p[i] = (uint8_t)(value >> (8 * i));
}

void mem_misaligned(uint32_t address, int size, int write_access)
{
    emu_abort(PC, "misaligned %s %d at %08x", write_access ? "write" : "read", size, address);
}

int hle_is_hook(uint32_t address)
{
    return address == stop_address || address == DELAY || address == GET_PARAM || address == WIFI;
}

int hle_check(cpu_t *cpu)
{
    uint32_t pc = cpu->regs[REG_PC];
    if (pc == stop_address) {
        reached_stop = 1;
        emu_stop = 1;
        return 1;
    }
    if (pc == DELAY) {
        delay_argument = cpu->regs[0];
        cpu->regs[0] = 0;
    } else if (pc == GET_PARAM) {
        parameter_id = cpu->regs[0];
        if (parameter_id != 0xf971 || cpu->regs[1] || cpu->regs[REG_A0])
            emu_abort(pc, "unexpected parameter getter arguments");
        if (!csv_mode) cpu->regs[0] = (uint32_t)parameter_value;
    } else if (pc == WIFI) {
        ++wifi_requests;
        cpu->regs[0] = 0;
    }
    return 0;
}

void soc_tick(uint64_t cycles) { emu_ns += cycles; }
uint64_t soc_next_event(void) { return emu_ns + 1; }

static int invoke(uint32_t target, uint8_t mask, uint8_t frame)
{
    uint32_t displacement = target - CALLER;
    uint8_t *p = stack_ram + CALLER - STACK;
    p[0] = 0xdd;
    for (unsigned i = 0; i < 4; ++i) p[i + 1] = (uint8_t)(displacement >> (i * 8));
    p[5] = mask;
    p[6] = frame;
    p[7] = 0xcb;
    stop_address = CALLER + 7;
    reached_stop = emu_stop = 0;
    cpus[0].regs[REG_PC] = CALLER;
    cpus[0].regs[REG_SP] = STACK + 0xf000;
    cpu_run(200000, 0);
    return reached_stop && cpus[0].regs[REG_SP] == STACK + 0xf000;
}

static int run_csv(void)
{
    const uint32_t context = STACK + 0x1000, line = STACK + 0x800, scratch = STACK + 0x2000;
    /* A synthetic zero-valued base entry isolates fallback from missing-key logs. */
    uint32_t entry = INDEX + (0xf971u >> 4) * 8;
    mem_wr(entry, 0x0001f971, 4);
    mem_wr(entry + 4, STACK + 0x400, 4);
    mem_wr(context + 36, RECORDS, 4);
    mem_wr(context + 40, 8188, 4);
    snprintf((char *)stack_ram + line - STACK, 64, "Wifi shell,0xF971,1,%d\n", parameter_value);
    cpus[0].regs[REG_A0] = context;
    cpus[0].regs[REG_A0 + 1] = line;
    cpus[0].regs[REG_D0] = scratch;
    if (!invoke(0x7e13ffa0, 0xf0, 36) || !invoke(0x7e140c16, 0x20, 8)) return 1;
    cpus[0].regs[0] = 0xf971;
    cpus[0].regs[1] = cpus[0].regs[REG_A0] = 0;
    if (!invoke(GET_PARAM, 0xc0, 12)) return 1;
    unsigned parsed = cpus[0].regs[0];
    stop_address = STOP;
    reached_stop = emu_stop = 0;
    cpus[0].regs[REG_PC] = 0x7e1c7f99;
    cpus[0].regs[REG_SP] = STACK + 0xf000;
    cpu_run(200000, 0);
    if (!reached_stop || wifi_requests != parameter_value) return 1;
    if (!invoke(0x7e140c47, 0, 0)) return 1;
    cpus[0].regs[0] = 0xf971;
    cpus[0].regs[1] = cpus[0].regs[REG_A0] = 0;
    if (!invoke(GET_PARAM, 0xc0, 12)) return 1;
    printf("{\"parameter_value\":%d,\"parsed_value\":%u,\"after_clear\":%u,\"wifi_requests\":%d,"
           "\"reached_stop\":true,\"instructions\":%llu}\n",
           parameter_value, parsed, cpus[0].regs[0], wifi_requests, (unsigned long long)cpus[0].icount);
    return parsed == (unsigned)parameter_value && cpus[0].regs[0] == 0 ? 0 : 1;
}

int main(int argc, char **argv)
{
    if ((argc != 3 && argc != 4) || (strcmp(argv[2], "0") && strcmp(argv[2], "1"))) return 2;
    if (argc == 4 && strcmp(argv[3], "csv")) return 2;
    csv_mode = argc == 4;
    parameter_value = argv[2][0] - '0';
    FILE *file = fopen(argv[1], "rb");
    image = malloc(IMAGE_BYTES);
    if (!file || !image) return 2;
    if (fread(image, 1, IMAGE_BYTES, file) != IMAGE_BYTES || fgetc(file) != EOF) return 2;
    fclose(file);
    cpus[0].running = 1;
    cpus[0].irq_level = 7;
    if (csv_mode) {
        int result = run_csv();
        free(image);
        return result;
    }
    cpus[0].regs[REG_PC] = 0x7e1c7f99;
    cpus[0].regs[REG_SP] = STACK + 32768;
    cpu_run(2000, 0);
    printf("{\"parameter_value\":%d,\"parameter_id\":%u,\"delay_argument\":%u,"
           "\"wifi_requests\":%d,\"reached_stop\":%s,\"instructions\":%llu}\n",
           parameter_value, parameter_id, delay_argument, wifi_requests,
           reached_stop ? "true" : "false", (unsigned long long)cpus[0].icount);
    free(image);
    return reached_stop ? 0 : 1;
}
