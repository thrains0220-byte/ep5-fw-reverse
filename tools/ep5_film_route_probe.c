/* SPDX-License-Identifier: GPL-3.0-or-later
 * Reuse the stock contract probe's checked memory map, ROM loader model and log sinks. */
#define main contract_probe_main
#define mem_rd contract_mem_rd
#define mem_wr contract_mem_wr
#define hle_is_hook contract_is_hook
#define hle_check contract_check
#include "ep5_contract_probe.c"
#undef main
#undef mem_rd
#undef mem_wr
#undef hle_is_hook
#undef hle_check

#define CONTEXT (STACK + 0x2000u)
#define JOB (STACK + 0x9000u)
#define SETTINGS (STACK + 0x9200u)
#define CACHE (STACK + 0xa000u)
#define WORDS (STACK + 0xa400u)
#define FRAME (STACK + 0xe000u)
#define MOV_PACKET (STACK + 0x500u)
#define MOV_TASK (STACK + 0x800u)
#define MOV_EFFECTS (STACK + 0xd00u)
#define OWNER (STACK + 0x1200u)
#define RAW_ENTRY (STACK + 0x1500u)
#define SECOND_TASK 0x605f6518u
static unsigned movie_fixture = 7;

/* Supply bounded RAM records for movie settings, recording state and RAW handle 1. */
uint32_t mem_rd(uint32_t a, int n)
{
    if (within(a, n, 0x605e9524, 9)) return contract_mem_rd(MOV_EFFECTS + a - 0x605e9524, n);
    if (within(a, n, 0x605ea1e0, 36))
        return a == 0x605ea200 && n == 4 && movie_fixture == 9;
    /* States 8/9 additionally consult a boolean and the selected 140-byte
     * recording configuration. Model index 0 and its two read fields only. */
    if ((a == 0x605e95c2 && n == 1) || (a == 0xa087dd50 && n == 2) ||
        (a == 0xa087dbb0 && n == 4) || (a == 0xa087dc0c && n == 1)) return 0;
    if (within(a, n, 0x60546970, 20)) return contract_mem_rd(RAW_ENTRY + a - 0x60546970, n);
    return contract_mem_rd(a, n);
}

/* The second ART task ring is used when the REC stage selector is 1 or 2. */
void mem_wr(uint32_t a, uint32_t value, int n)
{
    if (!within(a, n, SECOND_TASK, 676)) {
        contract_mem_wr(a, value, n);
        return;
    }
    uint8_t *dest = mem_host(a, n);
    for (int i = 0; i < n; ++i) dest[i] = (uint8_t)(value >> (8 * i));
}

static uint32_t boundary, submit;
static int driver_mode = -1;
static const uint32_t endpoints[] = {0x7e3a94ba, 0x7e3ed818, 0x7e40d23a, 0x7e40d54f,
    0x7e2291b9, 0x7e3f9443, 0x7e3f28a0, 0x7e3f2a49, 0x7e3f4884};

int hle_is_hook(uint32_t pc)
{
    for (size_t i = 0; i < sizeof endpoints / sizeof *endpoints; ++i)
        if (pc == endpoints[i]) return 1;
    return pc == 0x7e409654 || pc == 0x7e23d708 || pc == 0x7e229ff0 || contract_is_hook(pc);
}

int hle_check(cpu_t *cpu)
{
    uint32_t pc = cpu->regs[REG_PC];
    if (pc == 0x7e40d23a || pc == 0x7e40d54f) submit = pc;
    if (pc == boundary) {
        stopped = emu_stop = 1;
        return 1;
    }
    /* Request acquisition and address translation are external to this probe.
     * Their callers allocate the frames; execute each matching stock RET. */
    if (pc == 0x7e409654) {
        if (cpu->regs[REG_D0] != 0x20000000) emu_abort(pc, "unexpected request kind");
        cpu->regs[REG_A0] = JOB;
        cpu->regs[REG_PC] = 0x7e409722;
    } else if (pc == 0x7e23d708) {
        if (cpu->regs[REG_D0] != 1) emu_abort(pc, "unexpected RAW buffer index");
        cpu->regs[REG_D0] = STACK + 0x1000;
        cpu->regs[REG_PC] = 0x7e23d7de;
    } else {
        if (pc == 0x7e229ff0) driver_mode = mem_rd(cpu->regs[REG_SP] + 40, 1);
        return contract_check(cpu);
    }
    return 1;
}

static int run_section(uint32_t start, uint32_t end)
{
    boundary = end;
    cpus[0].regs[REG_PC] = start;
    cpus[0].regs[REG_SP] = FRAME;
    stopped = emu_stop = 0;
    cpu_run(10000, 0);
    return stopped && cpus[0].regs[REG_PC] == end;
}

static int build_list(uint32_t task, uint32_t packet)
{
    put(MESSAGE, 3, 4);
    put(MESSAGE + 12, packet, 4);
    cpus[0].regs[REG_D0] = task;
    cpus[0].regs[REG_A0] = MESSAGE;
    cpus[0].regs[REG_A0 + 1] = packet;
    put(CALLER, 0xdd, 1);
    put(CALLER + 1, 0x7e40b368 - CALLER, 4);
    put(CALLER + 5, 0x24f0, 2);
    return run_section(CALLER, CALLER + 7);
}

int main(int argc, char **argv)
{
    if ((argc != 4 && argc != 5) || (strcmp(argv[3], "200") && strcmp(argv[3], "3200")) || strlen(argv[2]) != 1 || argv[2][0] < '1' || argv[2][0] > '4')
        return 2;
    if (argc == 5) {
        if (strlen(argv[4]) != 1 || argv[4][0] < '7' || argv[4][0] > '9') return 2;
        movie_fixture = argv[4][0] - '0';
    }
    FILE *f = fopen(argv[1], "rb");
    image = malloc(IMAGE_BYTES);
    if (!f || !image || fread(image, 1, IMAGE_BYTES, f) != IMAGE_BYTES || fgetc(f) != EOF)
        return 2;
    fclose(f);
    mode = 2;  /* Stock contract probe's non-boot, non-chroma service model. */
    cpus[0].running = 1;
    cpus[0].irq_level = 7;
    uint32_t *r = cpus[0].regs;
    put(CONTEXT + 17471, 105, 1);
    put(CONTEXT + 18147, argv[2][0] - '0', 1);
    /* MOV derives state 7 from owner bit 0, and 8/9 from global +32 when
     * the bit is clear. The resulting state is read back from the packet. */
    put(OWNER, movie_fixture == 7, 4);
    put(OWNER + 43, 105, 1);
    put(MOV_EFFECTS + 1, argv[2][0] - '0', 1);
    r[REG_A0] = OWNER;
    r[REG_A0 + 1] = MOV_PACKET;
    if (!run_section(0x7e3a9471, 0x7e3a94ba)) return 1;
    if (!build_list(MOV_TASK, MOV_PACKET)) return 1;

    /* Enter the REC wrapper with synthetic capture state. It derives the packet type,
     * mode, effects and stage selector before consulting art_GetCaptureSupport. */
    put(OWNER + 84, CONTEXT, 4);
    put(OWNER + 122, atoi(argv[3]), 2);
    r[REG_A0] = OWNER;
    if (!run_section(0x7e3ed7e6, 0x7e3ed818)) return 1;
    unsigned packet_mode = mem_rd(PACKET + 6, 2);
    unsigned gate = r[REG_D0];
    unsigned stage = mem_rd(PACKET + 4, 2);
    uint32_t queue = stage == 0 ? TASK : SECOND_TASK;
    if (gate == 0) {
        /* Model the queue message and image metadata supplied after capture. */
        if (!build_list(TASK, PACKET)) return 1;
        put(JOB + 96, SETTINGS, 4);
        put(PACKET + 44, 1, 4);       /* Valid RAW handle and its table entry. */
        put(RAW_ENTRY, 3, 2);
        put(RAW_ENTRY + 2, 1, 2);
        put(RAW_ENTRY + 12, CONTEXT, 4);
        put(PACKET + 96, 1, 1);
        put(PACKET + 166, 3, 1);
        /* Dispatch the actual initializer from the selected ring, on its wrapper.
         * Only the underlying allocator is modeled. Firmware chooses the size
         * and stores the buffer and geometry later consumed by the JPEG request. */
        r[REG_A0] = queue + 8;
        put(CALLER, 0xdd, 1);
        put(CALLER + 1, mem_rd(queue + 4, 4) - CALLER, 4);
        put(CALLER + 5, 0, 2);
        if (!run_section(CALLER, CALLER + 7) || r[REG_D0] != 0) return 1;
        /* Dispatch the installed converter with its initialized wrapper.
         * Stock pass 1 and the table walker choose the submitting pass. */
        r[REG_A0] = queue + 8;
        uint32_t submission = stage == 0 ? 0x7e40d54f : 0x7e40d23a;
        if (!run_section(mem_rd(queue + 60, 4), submission)) return 1;
        if (r[REG_A0] != (stage == 0 ? JOB : PACKET) ||
            r[REG_A0 + 1] != (stage == 0 ? PACKET : JOB)) return 1;

        /* Queue delivery and hardware are outside this fixture. Hand the original
         * job pointer to the driver's cold-cache curve builder with flag 4096. */
        put(FRAME + 4, WORDS, 4);
        put(FRAME + 8, 0, 4);
        r[REG_D0] = 4096;
        r[REG_D0 + 1] = CACHE;
        r[REG_A0] = STACK + 0xb000;
        r[REG_A0 + 1] = JOB;
        if (!run_section(0x7e2291b4, 0x7e2291b9) || r[REG_D0] != 1) return 1;
    }
    /* Exercise both output-type branches of rec_make_image on the same REC
     * context. These are two synthetic requests, not a simulated RAW+JPEG save. */
    put(OWNER + 88, 0x1001, 2);
    put(OWNER + 112, 3, 2);
    r[REG_A0] = OWNER;
    if (!run_section(0x7e3f26a8, 0x7e3f9443) || r[REG_A0] != OWNER) return 1;
    uint32_t orf_return = r[REG_MDR];
    put(OWNER + 112, 1, 2);
    r[REG_A0] = OWNER;
    if (!run_section(0x7e3f26a8, 0x7e3f28a0) || r[REG_A0] != OWNER) return 1;
    uint32_t jpeg_return = r[REG_MDR];
    /* Skip the JPEG resource setup, resuming at the real call to its selector.
     * Do not initialize pixel data or execute the encoder or either file writer. */
    r[REG_A0 + 3] = OWNER;
    if (!run_section(0x7e3f2909, gate ? 0x7e3f2a49 : 0x7e3f4884)) return 1;
    uint32_t request = r[REG_A0 + 1];
    if (!gate && (r[REG_A0] != OWNER || !within(request, 40, STACK, sizeof stack_ram))) return 1;
    printf("{\"orf_dispatch_return\":%u,\"jpeg_dispatch_return\":%u,\"jpeg_target\":%u,"
           "\"allocation_calls\":%u,\"allocation_bytes\":%u,\"art_buffer\":%u,\"codec\":",
           orf_return, jpeg_return, r[REG_PC], allocation_calls, allocation_bytes, mem_rd(PACKET + 76, 4));
    if (gate) printf("null");
    else printf("{\"return\":%u,\"buffer\":%u,\"kind\":%u,\"geometry\":[%u,%u,%u,%u]}",
                r[REG_MDR], mem_rd(request, 4), mem_rd(request + 28, 4),
                mem_rd(request + 4, 2), mem_rd(request + 6, 2),
                mem_rd(request + 8, 2), mem_rd(request + 10, 2));
    printf(",\"movie_mode\":%u,\"movie_kind\":%u,\"movie_state\":%u,"
           "\"movie_entry\":%u,\"movie_next\":%u,\"stage\":%u,\"submit\":%u,"
           "\"packet_mode\":%u,\"gate\":%u,\"converter\":%u,\"filter\":%u,"
           "\"work_mode\":%u,\"job\":%u,\"driver_mode\":%d,\"words_hex\":\"",
           mem_rd(MOV_PACKET + 6, 2), mem_rd(MOV_PACKET, 2), mem_rd(MOV_PACKET + 2, 2),
           mem_rd(MOV_TASK + 60, 4), mem_rd(MOV_TASK + 68, 4), stage, submit, packet_mode,
           gate, mem_rd(queue + 60, 4), mem_rd(TASK + (stage == 0 ? 68 : 60), 4),
           mem_rd(SETTINGS + 87, 1), mem_rd(JOB + 194, 1), driver_mode);
    if (driver_mode >= 0)
        for (int i = 0; i < 34 * 4; ++i) printf("%02x", mem_rd(WORDS + i, 1));
    puts("\"}");
    free(image);
    return 0;
}
