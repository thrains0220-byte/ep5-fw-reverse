/* SPDX-License-Identifier: GPL-3.0-or-later
 * Execute compiled colour instructions in synthetic memory, without camera I/O.
 */
#include "emu.h"

#define CODE 0x20000000u
#define DONE 0x2000fff0u
#define STACK 0x10000000u
#define CONFIG 0x11000000u
#define PIXELS 0x12000000u
#define LUT 0x13000000u

static uint8_t code[65536], stack_ram[65536], config[32], pixels[65536], lut[29478];
static uint8_t stop_bytes[8] = {0xcb, 0xcb, 0xcb, 0xcb, 0xcb, 0xcb, 0xcb, 0xcb};
static uint32_t code_size, pixel_size;
static int reached_stop;
uint64_t emu_ns;

static int within(uint32_t address, uint32_t length, uint32_t base, uint32_t size)
{
    return address >= base && (uint64_t)address + length <= (uint64_t)base + size;
}

uint8_t *mem_host(uint32_t address, uint32_t length)
{
    if (within(address, length, CODE, code_size)) return code + address - CODE;
    if (within(address, length, STACK, sizeof stack_ram)) return stack_ram + address - STACK;
    if (within(address, length, CONFIG, sizeof config)) return config + address - CONFIG;
    if (within(address, length, PIXELS, pixel_size)) return pixels + address - PIXELS;
    if (within(address, length, LUT, sizeof lut)) return lut + address - LUT;
    if (within(address, length, DONE, sizeof stop_bytes)) return stop_bytes + address - DONE;
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
    if (!within(address, size, STACK, sizeof stack_ram) &&
        !within(address, size, PIXELS, pixel_size) && !within(address, size, CONFIG + 28, 4))
        emu_abort(PC, "write outside pixels/result/stack %08x", address);
    uint8_t *p = mem_host(address, (uint32_t)size);
    for (int i = 0; i < size; ++i) p[i] = (uint8_t)(value >> (8 * i));
}

void mem_misaligned(uint32_t address, int size, int write_access)
{
    emu_abort(PC, "misaligned %s %d at %08x", write_access ? "write" : "read", size, address);
}

int hle_is_hook(uint32_t address) { return address == DONE; }
int hle_check(cpu_t *cpu)
{
    (void)cpu;
    reached_stop = emu_stop = 1;
    return 1;
}
void soc_tick(uint64_t cycles) { emu_ns += cycles; }
uint64_t soc_next_event(void) { return emu_ns + 1; }

static size_t load_file(const char *path, uint8_t *destination, size_t capacity)
{
    FILE *file = fopen(path, "rb");
    if (!file) { perror(path); exit(2); }
    size_t size = fread(destination, 1, capacity, file);
    if (ferror(file) || fgetc(file) != EOF) { fprintf(stderr, "input exceeds bounds\n"); exit(2); }
    fclose(file);
    return size;
}

int main(int argc, char **argv)
{
    if (argc != 6) return 2;
    code_size = load_file(argv[1], code, sizeof code);
    pixel_size = load_file(argv[3], pixels, sizeof pixels);
    if (!code_size || code_size >= DONE - CODE || !pixel_size ||
        load_file(argv[2], lut, sizeof lut) != sizeof lut ||
        load_file(argv[4], config, sizeof config) != sizeof config) return 2;
    cpus[0].running = 1;
    cpus[0].irq_level = 7;
    cpus[0].regs[REG_PC] = CODE;
    cpus[0].regs[REG_SP] = STACK + 0xf000;
    cpu_run(50000000, 0);
    if (!reached_stop) return 1;
    FILE *file = fopen(argv[5], "wb");
    if (!file || fwrite(pixels, 1, pixel_size, file) != pixel_size || fclose(file)) return 2;
    printf("{\"result_u32\":%u,\"instructions\":%llu,\"reached_stop\":true}\n",
           mem_rd(CONFIG + 28, 4), (unsigned long long)cpus[0].icount);
    return 0;
}
