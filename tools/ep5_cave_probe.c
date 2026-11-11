/* SPDX-License-Identifier: GPL-3.0-or-later
 * Execute original ART code, a cave overlay and compiled colour instructions.
 * Native receiver executes; kernel queue/log/codec/free are modeled. No ISP. */
#include "emu.h"

#define BASE 0x7e101020u
#define IMAGE_BYTES 15728576u
#define CAVE 0x7e128010u
#define CAVE_BYTES 32752u
#define HOOK 0x7e3ed8d1u
#define STACK 0x60000000u
#define CALLER (STACK + 0x100u)
#define CONTEXT 0x11000000u
#define PIXELS 0x12000000u
#define ART_GLOBAL 0x605f455cu
#define CODEC 0x7e3f4884u
#define LOGGER 0x7e3f0464u
#define WAIT_HOOK 0x7e3ed850u
#define RECEIVER 0x7e3f7fa7u
#define UNCAVE (CAVE + 0x40000000u)
#define RELEASE_HOOK 0x7e3f2476u
#define FREE_BUFFER 0x7e23e0b0u
#define QUEUE_READ 0x7e117c7cu
#define QUEUE_ROUTE 0x7e132fdeu
#define QUEUE_ERROR 0x7e132ed3u
#define ERROR_LOG 0x7e106c9du

static uint8_t *image, stack_ram[65536], context[0x4600], globals[16], pixels[65536];
static uint8_t rec_return[8] = {0xdf, 0xa0, 12}, codec_return[8] = {0xdf, 0xf0, 16};
static uint8_t queue_return[8] = {0xdf, 0xf0, 32}, route_return[8] = {0xdf, 0xc0, 16};
static uint8_t error_return[8] = {0xdf, 0xf0, 124}, error_log_return[8] = {0xdf, 0xa0, 40};
static uint8_t free_return[8] = {0xdf, 0x00, 4};
static uint32_t pixel_bytes, registers_at_hook[8], mdr_at_hook, sp_at_hook, request[10];
static unsigned hook_count, codec_calls;
static uint32_t bridge_call;
static unsigned bridge_count;
static uint32_t state_offset, wait_call, wait_registers[8], wait_sp;
static uint8_t config[68];
static unsigned wait_calls;
static int wait_preserved = 1;
static int wait_return_preserved = 1;
static uint32_t returned_registers[8], returned_mdr;
static unsigned release_calls, state_writes;
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
    if (within(address, size, QUEUE_READ, 8)) return queue_return + (address - QUEUE_READ);
    if (within(address, size, QUEUE_ROUTE, 8)) return route_return + (address - QUEUE_ROUTE);
    if (within(address, size, QUEUE_ERROR, 8)) return error_return + (address - QUEUE_ERROR);
    if (within(address, size, ERROR_LOG, 8)) return error_log_return + (address - ERROR_LOG);
    if (within(address, size, FREE_BUFFER, 8)) return free_return + (address - FREE_BUFFER);
    if (within(address, size, BASE, IMAGE_BYTES)) return image + (address - BASE);
    if (within(address, size, STACK, sizeof stack_ram)) return stack_ram + (address - STACK);
    if (within(address, size, STACK + 0x40000000u, sizeof stack_ram))
        return stack_ram + (address - STACK - 0x40000000u);
    if (within(address, size, CONTEXT, sizeof context)) return context + (address - CONTEXT);
    if (within(address, size, ART_GLOBAL, sizeof globals)) return globals + (address - ART_GLOBAL);
    if (within(address, size, PIXELS, pixel_bytes)) return pixels + (address - PIXELS);
    if (within(address, size, UNCAVE, CAVE_BYTES)) return image + (CAVE - BASE) + (address - UNCAVE);
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
        !within(address, (uint32_t)size, STACK + 0x40000000u, sizeof stack_ram) &&
        !within(address, (uint32_t)size, PIXELS, pixel_bytes) &&
        !within(address, (uint32_t)size, ART_GLOBAL, 4) &&
        !within(address, (uint32_t)size, UNCAVE + state_offset, 8))
        emu_abort(PC, "write outside stack/pixels/qualification %08x", address);
    uint8_t *p = mem_host(address, (uint32_t)size);
    if (within(address, (uint32_t)size, UNCAVE + state_offset, 8)) ++state_writes;
    for (int i = 0; i < size; ++i) p[i] = (uint8_t)(value >> (8 * i));
}

void mem_misaligned(uint32_t address, int size, int write_access)
{
    emu_abort(PC, "misaligned access %08x size %d write %d", address, size, write_access);
}

int hle_is_hook(uint32_t address)
{
    return address == HOOK || address == bridge_call || address == CODEC || address == LOGGER ||
           address == WAIT_HOOK || address == RECEIVER || address == CALLER + 7 ||
           address == 0x7e3ed857 || address == FREE_BUFFER || address == 0x7e3f247b ||
           address == QUEUE_READ || address == QUEUE_ROUTE || address == wait_call + 7;
}

static uint32_t word(const uint8_t *p);

int hle_check(cpu_t *cpu)
{
    uint32_t pc = cpu->regs[REG_PC];
    if (pc == CALLER + 7 || pc == 0x7e3f247b) { reached_stop = emu_stop = 1; return 1; }
    if (pc == WAIT_HOOK) {
        memcpy(wait_registers, cpu->regs, sizeof wait_registers);
        wait_sp = cpu->regs[REG_SP];
        /* A short receive must not inherit a previously valid response. */
        uint32_t reply = cpu->regs[REG_A0];
        mem_wr(reply, 0, 4); mem_wr(reply + 4, 1, 4); mem_wr(reply + 8, 0x605f4510, 4);
    }
    if (pc == RECEIVER) {
        for (unsigned i = 0; i < 8; ++i) wait_preserved &= wait_registers[i] == cpu->regs[i];
        wait_preserved &= cpu->regs[REG_SP] == wait_sp - 32 && cpu->regs[REG_MDR] == wait_call + 7;
        uint32_t p = cpu->regs[REG_A0];
        if (!within(p, 12, STACK, sizeof stack_ram) || cpu->regs[REG_D0] != 0x123 ||
            cpu->regs[REG_D0 + 1] != 12 || cpu->regs[REG_A0 + 1] != 0xffffffff)
            emu_abort(pc, "bad original receive arguments");
    }
    if (pc == QUEUE_ROUTE) cpu->regs[REG_D0] = 0;
    if (pc == QUEUE_READ) {
        uint32_t p = cpu->regs[REG_A0];
        if (!within(p, 12, STACK, sizeof stack_ram) || cpu->regs[REG_D0] != 0x123 ||
            cpu->regs[REG_D0 + 1] != 0xffffffff)
            emu_abort(pc, "bad native kernel queue arguments");
        int32_t received = (int32_t)word(config + 40);
        if (received >= 0) {
            unsigned n = received < 12 ? (unsigned)received : 12;
            for (unsigned i = 0; i < n; ++i) mem_wr(p + i, config[44 + i], 1);
        }
        cpu->regs[REG_D0] = (uint32_t)received;
        cpu->regs[REG_D0 + 1] = 0xaced;
        cpu->regs[REG_A0] = 0x10203040;
        cpu->regs[REG_A0 + 1] = 0x50607080;
        ++wait_calls;
    }
    if (pc == wait_call + 7) {
        memcpy(returned_registers, cpu->regs, sizeof returned_registers);
        returned_mdr = cpu->regs[REG_MDR];
        int32_t kernel_result = (int32_t)word(config + 40);
        uint32_t result = kernel_result == -50 ? 0xfffffffeu : kernel_result < 0 ? 0xffffffffu : 0;
        if (cpu->regs[REG_D0] != result)
            emu_abort(pc, "unexpected original queue wrapper result");
    }
    if (pc == 0x7e3ed857) {
        for (unsigned i = 0; i < 8; ++i) wait_return_preserved &= cpu->regs[i] == returned_registers[i];
        wait_return_preserved &= cpu->regs[REG_SP] == wait_sp && cpu->regs[REG_MDR] == returned_mdr;
    }
    if (pc == FREE_BUFFER) {
        if (cpu->regs[REG_D0] != word(config + 36)) emu_abort(pc, "incorrect native free argument");
        if (word(config + 4) == 1 && word(config) == 0x43355045 &&
            (mem_rd(UNCAVE + state_offset, 4) || mem_rd(UNCAVE + state_offset + 4, 4)))
            emu_abort(pc, "qualification survived release");
        ++release_calls;
    }
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
        if (hook_count != codec_calls + 1) emu_abort(pc, "native codec without unique entry");
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

static void release_buffer(void)
{
    reached_stop = emu_stop = 0;
    cpus[0].regs[REG_PC] = RELEASE_HOOK - 1;
    cpus[0].regs[REG_A0 + 2] = CONTEXT;
    uint32_t saved_regs[4];
    for (unsigned i = 0; i < 4; ++i) saved_regs[i] = cpus[0].regs[i < 2 ? i + 2 : i + 4];
    cpu_run(50000, 0);
    if (!reached_stop || cpus[0].regs[REG_SP] != STACK + 0xf000 || mem_rd(ART_GLOBAL, 4))
        emu_abort(PC, "native release/frame failed");
    for (unsigned i = 0; i < 4; ++i)
        if (saved_regs[i] != cpus[0].regs[i < 2 ? i + 2 : i + 4])
            emu_abort(PC, "native release clobbered nonvolatile register");
}

int main(int argc, char **argv)
{
    if (argc != 12) return 2;
    uint8_t payload[CAVE_BYTES];
    image = malloc(IMAGE_BYTES);
    if (!image || load(argv[1], image, IMAGE_BYTES) != IMAGE_BYTES || load(argv[3], config, 68) != 68) return 2;
    size_t payload_bytes = load(argv[2], payload, CAVE_BYTES);
    char *tail;
    unsigned long control_offset = strtoul(argv[6], &tail, 10);
    if (*tail || !payload_bytes || payload_bytes < 24 || control_offset > payload_bytes - 24 || (control_offset & 3)) return 2;
    unsigned long call_offset = strtoul(argv[7], &tail, 10);
    if (*tail || call_offset > payload_bytes - 7 || payload[call_offset] != 0xdd ||
        payload[call_offset + 5] != 0xf0 || payload[call_offset + 6] != 16) return 2;
    bridge_call = CAVE + (uint32_t)call_offset;
    unsigned long state = strtoul(argv[8], &tail, 10);
    if (*tail || state > payload_bytes - 8 || (state & 3)) return 2;
    state_offset = (uint32_t)state;
    unsigned long wait_entry = strtoul(argv[9], &tail, 10);
    if (*tail || wait_entry >= payload_bytes) return 2;
    unsigned long wait_offset = strtoul(argv[10], &tail, 10);
    if (*tail || wait_offset > payload_bytes - 7 || payload[wait_offset] != 0xdd ||
        payload[wait_offset + 5] != 0 || payload[wait_offset + 6] != 20) return 2;
    wait_call = CAVE + (uint32_t)wait_offset;
    unsigned long release_entry = strtoul(argv[11], &tail, 10);
    if (*tail || release_entry >= payload_bytes) return 2;
    const uint8_t expected[] = {0xcd, 0xb3, 0x6f, 0xf0, 0x10};
    if (memcmp(image + (HOOK - BASE), expected, 5)) return 2;
    const uint8_t expected_wait[] = {0xdd, 0x57, 0xa7, 0, 0, 0, 20};
    if (memcmp(image + (WAIT_HOOK - BASE), expected_wait, 7)) return 2;
    const uint8_t expected_release[] = {0xcd, 0x4b, 0xb6, 0, 4};
    if (memcmp(image + (RELEASE_HOOK - BASE), expected_release, 5)) return 2;
    for (unsigned i = 0; i < CAVE_BYTES; ++i) if (image[CAVE - BASE + i] != 255) return 2;
    memcpy(payload + control_offset, config, 24);
    memcpy(image + (CAVE - BASE), payload, payload_bytes);
    image[HOOK - BASE] = 0xdc;
    put(image + (HOOK - BASE) + 1, CAVE - HOOK);
    image[WAIT_HOOK - BASE] = 0xdc;
    put(image + (WAIT_HOOK - BASE) + 1, CAVE + (uint32_t)wait_entry - WAIT_HOOK);
    image[WAIT_HOOK - BASE + 5] = image[WAIT_HOOK - BASE + 6] = 0xcb;
    image[RELEASE_HOOK - BASE] = 0xdc;
    put(image + (RELEASE_HOOK - BASE) + 1, CAVE + (uint32_t)release_entry - RELEASE_HOOK);
    pixel_bytes = (uint32_t)load(argv[4], pixels, sizeof pixels);
    if (!pixel_bytes) return 2;
    put(context + 84, CONTEXT + 0x100);
    context[0x100 + 17454] = (uint8_t)word(config + 32);
    put(globals, word(config + 36));
    memcpy(globals + 4, config + 24, 8);
    uint8_t *caller = stack_ram + (CALLER - STACK);
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
    unsigned art_result = 0;
    if (word(config + 40) != 0x7fffffffu) {
        put(globals, word(config + 64));
        put(caller + 1, 0x7e3ed843u - CALLER);
        caller[6] = 44;
        put(stack_ram + 0xf000 - 44 + 4, 0x123);
        cpus[0].regs[REG_D0 + 2] = 0;
        cpus[0].regs[REG_A0 + 3] = word(config + 56);
        cpu_run(50000, 0);
        art_result = cpus[0].regs[REG_D0];
        if (!reached_stop || !wait_preserved || !wait_return_preserved || cpus[0].regs[REG_SP] != STACK + 0xf000 || art_result != 0) return 1;
        put(globals, word(config + 36));
        put(caller + 1, 0x7e3ed85cu - CALLER);
        caller[6] = 56;
        reached_stop = emu_stop = 0;
        for (unsigned i = 0; i < 8; ++i) cpus[0].regs[i] = 0xabcd1000u + i;
        cpus[0].regs[REG_A0] = CONTEXT;
        cpus[0].regs[REG_PC] = CALLER;
    }
    unsigned repeats = word(config + 60);
    if (repeats < 1 || repeats > 3) return 2;
    if (repeats == 3) {
        release_buffer();
        /* Synthetic address reuse, with no second completion. */
        put(globals, word(config + 36));
        reached_stop = emu_stop = 0;
        for (unsigned i = 0; i < 8; ++i) cpus[0].regs[i] = 0xabcd1000u + i;
        cpus[0].regs[REG_A0] = CONTEXT;
        cpus[0].regs[REG_PC] = CALLER;
        repeats = 1;
    }
    cpu_run(50000000, 0);
    uint8_t first_pixels[65536];
    memcpy(first_pixels, pixels, pixel_bytes);
    if (repeats == 2) {
        reached_stop = emu_stop = 0;
        cpus[0].regs[REG_PC] = CALLER;
        cpus[0].regs[REG_A0] = CONTEXT;
        cpu_run(50000000, 0);
    }
    int preserved = cpus[0].regs[REG_SP] == STACK + 0xf000;
    for (unsigned i = 0; i < 4; ++i) preserved &= cpus[0].regs[saved[i]] == 0xabcd1000u + saved[i];
    if (!reached_stop || !preserved || !arguments_preserved || codec_calls != repeats || bridge_count != repeats || cpus[0].regs[REG_D0] != 0x1234) {
        fprintf(stderr, "native handoff failed: stop=%d preserved=%d arguments=%d hooks=%u codec=%u result=%x sp=%x\n",
                reached_stop, preserved, arguments_preserved, hook_count, codec_calls,
                cpus[0].regs[REG_D0], cpus[0].regs[REG_SP]);
        return 1;
    }
    uint32_t native_result = cpus[0].regs[REG_D0];
    release_buffer();
    FILE *out = fopen(argv[5], "wb");
    if (!out || fwrite(pixels, 1, pixel_bytes, out) != pixel_bytes || fclose(out)) return 2;
    printf("{\"codec_calls\":%u,\"native_result\":%u,\"native_arguments_preserved\":true,"
           "\"registers_and_stack_preserved\":true,\"instructions\":%llu,\"wait_calls\":%u,"
           "\"wait_arguments_preserved\":true,\"wait_return_preserved\":true,\"art_result\":%u,"
           "\"second_image_unchanged\":%s,\"release_calls\":%u,\"released_and_cleared\":true,\"state_writes\":%u}\n",
           codec_calls, native_result, (unsigned long long)cpus[0].icount, wait_calls,
           art_result, !memcmp(first_pixels, pixels, pixel_bytes) ? "true" : "false", release_calls, state_writes);
    free(image);
    return 0;
}
