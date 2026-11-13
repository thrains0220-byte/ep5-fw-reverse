/* SPDX-License-Identifier: GPL-3.0-or-later
 * No device or ISP. Reuse the checked E-P5 memory map and helper boundaries. */
#define main unused_contract_main
#define hle_is_hook contract_is_hook
#define hle_check contract_check
#include "ep5_contract_probe.c"
#undef main
#undef hle_is_hook
#undef hle_check
#define CONTEXT (STACK + 0x2000u)
#define OWNER (STACK + 0x1200u)
#define FRAME (STACK + 0xe000u)

static uint32_t end_pc;
int hle_is_hook(uint32_t pc) { return pc == end_pc || contract_is_hook(pc); }
int hle_check(cpu_t *cpu) {
    if (cpu->regs[REG_PC] == end_pc) { stopped = emu_stop = 1; return 1; }
    return contract_check(cpu);
}
static int run_section(uint32_t start, uint32_t end) {
    end_pc = end;
    cpus[0].regs[REG_PC] = start;
    cpus[0].regs[REG_SP] = FRAME;
    stopped = emu_stop = 0;
    cpu_run(20000, 0);
    return stopped && cpus[0].regs[REG_PC] == end;
}
static int build_list(void) {
    put(MESSAGE, 3, 4);
    put(MESSAGE + 12, PACKET, 4);
    cpus[0].regs[REG_D0] = TASK;
    cpus[0].regs[REG_A0] = MESSAGE;
    cpus[0].regs[REG_A0+1] = PACKET;
    put(CALLER, 0xdd, 1);
    put(CALLER + 1, 0x7e40b368 - CALLER, 4);
    put(CALLER + 5, 0x24f0, 2);
    return run_section(CALLER, CALLER + 7);
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    FILE *f = fopen(argv[1], "rb");
    image = malloc(IMAGE_BYTES);
    if (!f || !image || fread(image, 1, IMAGE_BYTES, f) != IMAGE_BYTES || fgetc(f) != EOF)
        return 2;
    fclose(f);
    printf("{\"writer\":");
    mode = CHROMA_MODE;
    if (probe_chroma()) return 1;
    printf(",\"routes\":[");
    /* This image byte indexes the REC capture settings, not the UI row or EXIF
     * ArtFilter. The range 100..202 is the selector's explicit range check. */
    unsigned rows = 0;
    for (unsigned setting = 100; setting <= 202; ++setting)
        for (unsigned v = 1; v <= 3; ++v) {
            memset(cpus, 0, sizeof(cpus[0]));
            memset(stack_ram, 0, sizeof(stack_ram));
            memset(ram, 0, sizeof(ram));
            mode = 2;
            cpus[0].running = 1;
            cpus[0].irq_level = 7;
            put(CONTEXT + 17471, setting, 1);
            put(CONTEXT + 18147, v, 1);
            put(OWNER + 84, CONTEXT, 4);
            put(OWNER + 122, 200, 2);
            cpus[0].regs[REG_A0] = OWNER;
            if (!run_section(0x7e3ed7e6, 0x7e3ed818)) return 1;
            unsigned gate = cpus[0].regs[REG_D0], packet = mem_rd(PACKET + 6, 2);
            if (gate == 0 && !build_list()) return 1;
            printf("%s[%u,%u,%u,%u,[", rows++ ? "," : "", setting, v, packet, gate);
            for (unsigned i = 0; i < 8; ++i) {
                unsigned fn = mem_rd(TASK + 60 + 8*i, 4);
                if (!fn) break;
                printf("%s%u", i ? "," : "", fn);
            }
            printf("]]");
        }
    puts("]}");
    free(image);
    return 0;
}
