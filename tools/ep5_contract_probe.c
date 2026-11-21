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
#define CHROMA_MODE 3
#define CHROMA_FRAME (STACK + 0xf000u)
#define CHROMA_WORDS (STACK + 0x3000u)
#define CHROMA_FLAGS (STACK + 0x3400u)
#define CHROMA_DEFAULT 0x602aad9cu
#define ART_REPLY_MODE 4
#define ART_REPLY_QUEUE 0xb3u
#define ART_REPLY_SEND 0x7e3fd694u
#define ART_REQUEST_SEND 0x7e3fd6d2u
#define ART_QUEUE_ROUTE 0x7e132fdeu
#define ART_QUEUE_READ 0x7e117c7cu
#define REC_SEND_TAIL 0x7e3ed822u
#define REC_WAIT_CALL 0x7e3ed850u
#define REC_STACK (STACK + 0xd000u)
#define ART_EFFECT_FIXTURE (STACK + 0x280u)
#define ART_TERMINAL_FIXTURE (STACK + 0x290u)
#define ART_TERMINAL_MAX_BYTES 128u
#define ART_WORK_RECORD (TASK + 4u)
#define ART_NEUTRAL_EFFECT 0x7e40cbb1u
#define ART_PINHOLE_EFFECT 0x7e40115cu
#define ART_PINHOLE_FINISH 0x7e401503u
#define ART_NEUTRAL_PASS7 0x7e40d620u
#define ART_NEUTRAL_ERROR 0x7e40d6f8u
#define ART_DISPATCH_PENDING 0x7e40b0ceu
#define ART_ISP_RESULT 0x7e40b8ebu
#define ART_ISP_SLOT (0x605f6d04u + 28u)
#define ART_ISP_SERVICE 0x7e10652bu

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
    {ART_REPLY_SEND, {0xdf, 0xf0, 16}}, /* records reply without sending it */
};
static const struct service art_transport[] = {
    {ART_REQUEST_SEND, {0xdf, 0xf0, 16}},
    {ART_QUEUE_ROUTE, {0xdf, 0xc0, 16}},
    {ART_QUEUE_READ, {0xdf, 0xf0, 32}},
};
static int mode, stopped, allocation_failed;
static int isp_ingesting;
static int rec_transport, rec_suspended;
static unsigned rec_sends, rec_reads;
static uint32_t rec_reply;
static unsigned allocation_calls, allocation_bytes, allocation_flags, errors;
static unsigned boot_source, boot_destination, boot_bytes;
static unsigned codec_calls, jpeg_buffer, jpeg_geometry[4];
static unsigned art_effect_status, art_effect_calls, art_reply_calls, art_reply_status;
static uint32_t art_reply_queue, art_reply_token, art_reply_packet;
static uint32_t art_reply_words[3];
static unsigned art_pass7_calls, art_error_calls, art_isp_service_calls;
static unsigned art_pinhole_finish_calls;
static unsigned art_neutral_finish_calls;
static uint32_t art_error_flags, art_reply_flags;
uint64_t emu_ns;

static int within(uint32_t a, uint32_t n, uint32_t base, uint32_t bytes)
{
    return a >= base && (uint64_t)a + n <= (uint64_t)base + bytes;
}

uint8_t *mem_host(uint32_t a, uint32_t n)
{
    /* For the default branch's zero auxiliary inputs, model one RAM entry using
     * an unmodified six-pointer ROM record. The hardware RAM table is unknown. */
    if (mode == CHROMA_MODE && within(a, n, CHROMA_DEFAULT, 24))
        return image + (0x7e478148u - BASE) + (a - CHROMA_DEFAULT);
    if (rec_transport)
        for (unsigned i = 0; i < sizeof art_transport / sizeof *art_transport; ++i)
            if (within(a, n, art_transport[i].pc, 8))
                return (uint8_t *)art_transport[i].ret + (a - art_transport[i].pc);
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
    if (mode == CHROMA_MODE &&
        !within(a, n, CHROMA_FRAME - 40, 40 + 132) &&
        !within(a, n, CHROMA_WORDS, 34 * 4) && !within(a, n, CHROMA_FLAGS, 4))
        emu_abort(PC, "write outside chroma call frame/output/flag %08x", a);
    if (!within(a, (uint32_t)n, STACK, sizeof stack_ram) &&
        !within(a, (uint32_t)n, PACKET, 396) &&
        !within(a, (uint32_t)n, TASK, 676) &&
        !(mode == ART_REPLY_MODE && within(a, (uint32_t)n, ART_ISP_SLOT, 28)) &&
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
    if (mode == CHROMA_MODE) return a == 0x7e22df82;
    if (a == CALLER + 7 || (mode == 0 && a == 0x7e10187b)) return 1;
    if (mode == ART_REPLY_MODE && (a == ART_EFFECT_FIXTURE || a == ART_TERMINAL_FIXTURE)) return 1;
    if (mode == ART_REPLY_MODE && (a == ART_NEUTRAL_PASS7 || a == ART_NEUTRAL_ERROR)) return 1;
    if (mode == ART_REPLY_MODE && a == ART_PINHOLE_FINISH) return 1;
    if (isp_ingesting && a == ART_ISP_SERVICE) return 1;
    if (rec_transport) {
        if (a == REC_WAIT_CALL && !rec_suspended) return 1;
        for (unsigned i = 0; i < sizeof art_transport / sizeof *art_transport; ++i)
            if (a == art_transport[i].pc) return 1;
    }
    for (unsigned i = 0; i < sizeof services / sizeof *services; ++i)
        if (a == services[i].pc) return 1;
    return 0;
}

int hle_check(cpu_t *cpu)
{
    uint32_t pc = cpu->regs[REG_PC];
    if (mode == CHROMA_MODE && pc == 0x7e22df82) { stopped = emu_stop = 1; return 1; }
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
    if (mode == ART_REPLY_MODE && pc == ART_EFFECT_FIXTURE) {
        if (cpu->regs[REG_A0] != ART_WORK_RECORD + 4)
            emu_abort(pc, "unexpected ART effect argument");
        ++art_effect_calls;
        cpu->regs[REG_D0] = art_effect_status;
    }
    if (mode == ART_REPLY_MODE && pc == ART_TERMINAL_FIXTURE) {
        if (cpu->regs[REG_A0] != ART_WORK_RECORD + 4)
            emu_abort(pc, "unexpected ART terminal argument");
        ++art_neutral_finish_calls;
    }
    if (rec_transport && pc == REC_WAIT_CALL && !rec_suspended) {
        rec_reply = cpu->regs[REG_SP] + 20;
        if (cpu->regs[REG_A0] != rec_reply || cpu->regs[REG_D0] != ART_REPLY_QUEUE ||
            cpu->regs[REG_D0 + 1] != 12 || cpu->regs[REG_A0 + 1] != UINT32_MAX ||
            !within(rec_reply, 12, STACK, sizeof stack_ram))
            emu_abort(pc, "unexpected REC wait frame");
        rec_suspended = emu_stop = 1;
        return 1;
    }
    if (rec_transport && pc == ART_REQUEST_SEND) {
        const uint32_t request = cpu->regs[REG_A0 + 1];
        if (!within(request, 16, STACK, sizeof stack_ram) ||
            cpu->regs[REG_D0] != 0xffff8001u || rec_sends)
            emu_abort(pc, "unexpected REC send arguments");
        for (unsigned offset = 0; offset < 16; offset += 4)
            mem_wr(MESSAGE + offset, mem_rd(request + offset, 4), 4);
        ++rec_sends;
        cpu->regs[REG_D0] = 0;
    }
    if (rec_transport && pc == ART_QUEUE_ROUTE) cpu->regs[REG_D0] = 0;
    if (rec_transport && pc == ART_QUEUE_READ) {
        if (cpu->regs[REG_A0] != rec_reply ||
            cpu->regs[REG_D0] != art_reply_queue || cpu->regs[REG_D0 + 1] != UINT32_MAX ||
            art_reply_calls != 1 || rec_reads)
            emu_abort(pc, "unexpected REC read arguments");
        for (unsigned i = 0; i < 3; ++i)
            mem_wr(rec_reply + 4 * i, art_reply_words[i], 4);
        ++rec_reads;
        cpu->regs[REG_D0] = 12;
    }
    if (mode == ART_REPLY_MODE &&
        (pc == ART_NEUTRAL_PASS7 || pc == ART_NEUTRAL_ERROR || pc == ART_PINHOLE_FINISH)) {
        if (cpu->regs[REG_A0] != PACKET || cpu->regs[REG_A0 + 1] != ART_WORK_RECORD + 4)
            emu_abort(pc, "unexpected ART stage arguments");
        if (pc == ART_NEUTRAL_PASS7) {
            ++art_pass7_calls;
        } else if (pc == ART_PINHOLE_FINISH) {
            ++art_pinhole_finish_calls;
        } else {
            ++art_error_calls;
            art_error_flags = mem_rd(ART_WORK_RECORD + 16, 4);
        }
    }
    if (isp_ingesting && pc == ART_ISP_SERVICE) {
        if (cpu->regs[REG_A0] != ART_ISP_SLOT + 12 ||
            cpu->regs[REG_D0] != 0 || cpu->regs[REG_D0 + 1] != 16)
            emu_abort(pc, "unexpected ART completion service arguments");
        ++art_isp_service_calls;
    }
    if (pc == ART_REPLY_SEND) {
        uint32_t reply = cpu->regs[REG_A0 + 1];
        if (mode != ART_REPLY_MODE || cpu->regs[REG_D0 + 1] != 12 ||
            !within(reply, 12, STACK, sizeof stack_ram))
            emu_abort(pc, "unexpected ART reply");
        ++art_reply_calls;
        art_reply_queue = cpu->regs[REG_D0];
        for (unsigned i = 0; i < 3; ++i)
            art_reply_words[i] = mem_rd(reply + 4 * i, 4);
        art_reply_status = mem_rd(reply, 2);
        art_reply_token = mem_rd(reply + 4, 4);
        art_reply_packet = mem_rd(reply + 8, 4);
        art_reply_flags = mem_rd(ART_WORK_RECORD + 16, 4);
        cpu->regs[REG_D0] = 0;
    }
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

/* Enter the stock caller after its path decision. (sp+124,sp+128) hold the
 * register block and flag addresses. Both native calls create their own frames. */
static int probe_chroma(void)
{
    printf("[");
    for (unsigned id = 0; id < 256; ++id) {
        cpu_t *cpu = &cpus[0];
        memset(cpu, 0, sizeof *cpu);
        memset(stack_ram, 0xa5, sizeof stack_ram);
        memset(stack_ram + (CHROMA_FRAME - STACK), 0, 132);
        put(CHROMA_FRAME + 124, CHROMA_WORDS, 4);
        put(CHROMA_FRAME + 128, CHROMA_FLAGS, 4);
        put(CHROMA_FLAGS, 0xa5a5a5a7u, 4);
        cpu->running = 1;
        cpu->irq_level = 7;
        cpu->regs[REG_PC] = 0x7e22df5b;
        cpu->regs[REG_SP] = CHROMA_FRAME;
        cpu->regs[REG_D0 + 2] = id;
        stopped = emu_stop = 0;
        cpu_run(20000, 0);
        if (!stopped || cpu->regs[REG_SP] != CHROMA_FRAME ||
            cpu->regs[REG_A0 + 2] != CHROMA_WORDS || cpu->regs[REG_A0 + 3] != CHROMA_FRAME + 56 ||
            cpu->regs[REG_D0 + 2] != 0 || cpu->regs[REG_D0 + 3] != 0 ||
            mem_rd(CHROMA_FLAGS, 4) != 0xa5a5a5a5u) {
            fprintf(stderr, "incomplete chroma call frame or flag for mode %u at %08x\n", id, cpu->regs[REG_PC]);
            return 1;
        }
        printf("%s{\"mode\":%u,\"flags\":%u,\"pointers\":[", id ? "," : "", id, mem_rd(CHROMA_FLAGS, 4));
        for (unsigned i = 0; i < 6; ++i)
            printf("%s%u", i ? "," : "", mem_rd(CHROMA_FRAME + 56 + 4 * i, 4));
        printf("],\"words\":[");
        for (unsigned i = 0; i < 34; ++i) {
            uint32_t word = mem_rd(CHROMA_WORDS + 4 * i, 4);
            if (word >> 24) {
                fprintf(stderr, "unwritten or invalid chroma word %u in mode %u\n", i, id);
                return 1;
            }
            printf("%s%u", i ? "," : "", word);
        }
        printf("]}");
    }
    puts("]");
    return 0;
}

static void prepare_art_call(uint32_t entry, uint32_t frame_mask, uint32_t frame_bytes,
                             uint32_t a0, uint32_t a1, uint32_t d0, uint32_t sp)
{
    uint8_t *call = stack_ram + (CALLER - STACK);
    uint32_t displacement = entry - CALLER;
    call[0] = 0xdd;
    for (unsigned i = 0; i < 4; ++i) call[1 + i] = (uint8_t)(displacement >> (8 * i));
    call[5] = (uint8_t)frame_mask;
    call[6] = (uint8_t)frame_bytes;
    cpu_t *cpu = &cpus[0];
    stopped = emu_stop = 0;
    cpu->running = 1;
    cpu->irq_level = 7;
    cpu->regs[REG_PC] = CALLER;
    cpu->regs[REG_SP] = sp;
    cpu->regs[REG_A0] = a0;
    cpu->regs[REG_A0 + 1] = a1;
    cpu->regs[REG_D0] = d0;
}

static int run_art_call(uint32_t entry, uint32_t frame_mask, uint32_t frame_bytes,
                        uint32_t a0, uint32_t a1, uint32_t d0)
{
    prepare_art_call(entry, frame_mask, frame_bytes, a0, a1, d0, STACK + 0xf000);
    cpu_run(20000, 0);
    cpu_t *cpu = &cpus[0];
    return stopped && cpu->regs[REG_SP] == STACK + 0xf000;
}

static int probe_art_reply(const char *name)
{
    const int pinhole = !strcmp(name, "isp-pinhole");
    const int empty_buffer = !strcmp(name, "isp-neutral-empty-buffer");
    const int neutral_finish = empty_buffer || !strcmp(name, "isp-neutral-finish");
    art_effect_status = !strcmp(name, "reply-pending") ? 1 :
                        !strcmp(name, "reply-failed") ? 0xffff : 2;
    const uint32_t token = pinhole || !strcmp(name, "reply-ready-custom-token") ? 0x21abc735u : 1;
    const uint8_t retf[] = {0xde, 0, 0};
    memcpy(stack_ram + (ART_EFFECT_FIXTURE - STACK), retf, sizeof retf);
    put(PACKET, 1, 2); /* still capture list */
    put(PACKET + 2, 3, 2);
    cpu_t suspended_rec;
    if (neutral_finish) {
        /* Pause REC at its blocking receive and dispatch ART on a separate stack. */
        rec_transport = 1;
        prepare_art_call(REC_SEND_TAIL, 0xb0, 44, 0, 0, 0, REC_STACK);
        cpus[0].regs[REG_A0 + 2] = PACKET;
        cpu_run(20000, 0);
        if (!rec_suspended || rec_sends != 1 || cpus[0].regs[REG_PC] != REC_WAIT_CALL ||
            mem_rd(MESSAGE, 4) != ART_REPLY_QUEUE || mem_rd(MESSAGE + 4, 4) != token ||
            mem_rd(MESSAGE + 8, 4) != 1 || mem_rd(MESSAGE + 12, 4) != PACKET)
            return 1;
        suspended_rec = cpus[0];
    } else {
        put(MESSAGE, ART_REPLY_QUEUE, 4);
        put(MESSAGE + 4, token, 4);
        put(MESSAGE + 8, 1, 4); /* ART execute command */
        put(MESSAGE + 12, PACKET, 4);
    }
    if (!strncmp(name, "isp-", sizeof "isp-" - 1)) {
        /* A synthetic completion record stands in for the device response.
         * The stock lookup, status update and (on failure) error handler run. */
        const uint32_t key = pinhole ? 0x03453739u : 0x03453607u;
        const uint32_t status = !strcmp(name, "isp-failed") ? 0x9a08u : 0;
        const int unknown = !strcmp(name, "isp-unknown");
        put(PACKET + 6, pinhole ? 73 : 0, 2);
        put(PACKET + 96, 1, 1); /* 4:3 geometry */
        if (!run_art_call(0x7e40b368, 0xf0, 36, MESSAGE, PACKET, TASK) ||
            cpus[0].regs[REG_D0] != 0 ||
            mem_rd(ART_WORK_RECORD, 4) != 0x7e40a20bu ||
            mem_rd(ART_WORK_RECORD + 56, 4) != ART_NEUTRAL_EFFECT ||
            mem_rd(ART_WORK_RECORD + 64, 4) != (pinhole ? ART_PINHOLE_EFFECT : 0)) return 1;
        /* Run the same initializer the worker would call. The pool is modeled. */
        if (!run_art_call(0x7e40a20b, 0, 0, ART_WORK_RECORD + 4, 0, 0) ||
            cpus[0].regs[REG_D0] != 0 || allocation_calls != 1 ||
            allocation_bytes != 4608u * 3456u * 2u) return 1;
        put(ART_WORK_RECORD, 0, 4); /* worker consumes the initializer once */
        if (pinhole) {
            /* Start after RAW development and pinhole passes 1–3 submitted
             * their work. The previously developed buffer and released scratch
             * pointers are fixture state. Execute both remaining stock passes. */
            put(ART_WORK_RECORD + 56, 0, 4);
            put(ART_WORK_RECORD + 40, mem_rd(PACKET + 76, 4), 4);
        }
        if (neutral_finish) {
            /* Test-only finalizer uses the existing worker's second slot.
             * It proves sequencing and replies, not physical buffer ownership. */
            put(ART_WORK_RECORD + 64, ART_TERMINAL_FIXTURE, 4);
            if (empty_buffer) put(PACKET + 76, 0, 4);
        }
        put(ART_WORK_RECORD + 16, pinhole ? 0x3ffffu : 0x1fu, 4);
        put(ART_WORK_RECORD + 20, 0x9a09u, 4);
        put(ART_ISP_SLOT, key, 4);
        put(ART_ISP_SLOT + 4, 0xc3b2a100u, 4); /* task index 0 and padding canary */
        put(ART_ISP_SLOT + 8, pinhole ? 0x40000u : 0x20u, 4);
        for (unsigned offset = 12; offset < 28; offset += 4)
            put(ART_ISP_SLOT + offset, 0x4f3e2d1cu, 4);
        put(ART_ISP_SLOT + 14, status, 2);
        isp_ingesting = 1;
        const int returned = run_art_call(ART_ISP_RESULT, 0xc0, 28, 0, 0, key + (unsigned)unknown);
        isp_ingesting = 0;
        if (!returned) return 1;
        const uint32_t flags = mem_rd(ART_WORK_RECORD + 16, 4);
        const uint32_t result = mem_rd(ART_WORK_RECORD + 20, 4);
        /* An unmatched result leaves pass 6 outstanding. Its ISP work is out of scope. */
        if (!unknown && !run_art_call(ART_DISPATCH_PENDING, 0xf0, 28, 0, 0, 0))
            return 1;
        /* On neutral-only success, another worker poll still cannot emit the reply. */
        if (!pinhole && !neutral_finish && !unknown && !status &&
            !run_art_call(ART_DISPATCH_PENDING, 0xf0, 28, 0, 0, 0)) return 1;
        if (pinhole || neutral_finish) {
            if (art_reply_calls != 1 || art_reply_status != (empty_buffer ? 0x9a06u : 0) ||
                art_reply_queue != ART_REPLY_QUEUE || art_reply_token != token || art_reply_packet != PACKET)
                return 1;
            uint32_t received_status = art_reply_status;
            if (neutral_finish) {
                cpus[0] = suspended_rec;
                stopped = emu_stop = 0;
                cpu_run(20000, 0);
                if (!stopped || cpus[0].regs[REG_SP] != REC_STACK || rec_reads != 1 ||
                    cpus[0].regs[REG_D0] != 0 || mem_rd(rec_reply, 2) != art_reply_status ||
                    mem_rd(rec_reply + 4, 4) != token || mem_rd(rec_reply + 8, 4) != PACKET)
                    return 1;
                received_status = mem_rd(rec_reply, 2);
            }
            /* The fixture drives the transition to the original JPEG constructor. */
            if (received_status == 0) {
                put(STACK + 0x3000 + 84, STACK + 0x3100, 4);
                if (!run_art_call(0x7e3ed85c, 0xb0, 56, STACK + 0x3000, 0, 0) ||
                    cpus[0].regs[REG_D0] != 0x1234) return 1;
            }
        }
        printf("{\"input_status\":%u,\"stage_flags\":%u,\"result_word\":%u,"
               "\"allocation_bytes\":%u,\"packet_buffer\":%u,"
               "\"completion_key_after\":%u,\"completion_index_and_padding_after\":%u,"
               "\"completion_mask_after\":%u,\"completion_tail_after\":[%u,%u,%u,%u],"
               "\"service_calls\":%u,\"errors\":%u,\"pass7_calls\":%u,"
               "\"pinhole_finish_calls\":%u,\"neutral_finish_calls\":%u,\"record_buffer_after\":%u,"
               "\"effect_after\":%u,\"error_handler_calls\":%u,"
               "\"error_handler_flags\":%u,\"reply_calls\":%u,\"reply_u16_status\":%u,"
               "\"reply_flags\":%u,\"queue\":%u,\"token\":%u,\"packet\":%u,\"task_cleared\":%s,"
               "\"rec_sends\":%u,\"rec_reads\":%u,"
               "\"codec_calls\":%u,\"jpeg_buffer\":%u,\"jpeg_geometry_u16\":[%u,%u,%u,%u]}\n",
               status, flags, result, allocation_bytes, mem_rd(PACKET + 76, 4),
               mem_rd(ART_ISP_SLOT, 4), mem_rd(ART_ISP_SLOT + 4, 4),
               mem_rd(ART_ISP_SLOT + 8, 4), mem_rd(ART_ISP_SLOT + 12, 4), mem_rd(ART_ISP_SLOT + 16, 4),
               mem_rd(ART_ISP_SLOT + 20, 4), mem_rd(ART_ISP_SLOT + 24, 4),
               art_isp_service_calls, errors, art_pass7_calls, art_pinhole_finish_calls, art_neutral_finish_calls,
               mem_rd(ART_WORK_RECORD + 40, 4),
               mem_rd(ART_WORK_RECORD + (pinhole ? 64 : 56), 4), art_error_calls, art_error_flags,
               art_reply_calls, art_reply_status, art_reply_flags,
               art_reply_queue, art_reply_token, art_reply_packet,
               mem_rd(ART_WORK_RECORD + 12, 4) == 0 ? "true" : "false",
               rec_sends, rec_reads,
               codec_calls, jpeg_buffer, jpeg_geometry[0], jpeg_geometry[1], jpeg_geometry[2], jpeg_geometry[3]);
        return 0;
    }

    /* Single effect in the first worker record. Only the callback is modeled. */
    if (!run_art_call(0x7e40b511, 0x30, 16, MESSAGE, PACKET, TASK)) return 1;
    put(ART_WORK_RECORD + 56, ART_EFFECT_FIXTURE, 4);
    if (!run_art_call(0x7e40b9b9, 0xf0, 56, ART_WORK_RECORD, 0, 0) ||
        art_effect_calls != 1) return 1;
    printf("{\"effect_calls\":%u,\"effect_status\":%u,\"reply_calls\":%u,\"queue\":%u,"
           "\"reply_u16_status\":%u,\"token\":%u,\"packet\":%u,\"task_cleared\":%s}\n",
           art_effect_calls, art_effect_status, art_reply_calls, art_reply_queue,
           art_reply_status, art_reply_token, art_reply_packet,
           mem_rd(ART_WORK_RECORD + 12, 4) == 0 ? "true" : "false");
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 3 || argc > 4) return 2;
    const char *name = argv[2];
    const int needs_terminal = !strcmp(name, "isp-neutral-finish") ||
                               !strcmp(name, "isp-neutral-empty-buffer");
    if (needs_terminal != (argc == 4)) return 2;
    if (!strcmp(name, "boot")) mode = 0;
    else if (!strcmp(name, "chroma")) mode = CHROMA_MODE;
    else if (!strcmp(name, "reply-ready") || !strcmp(name, "reply-pending") ||
             !strcmp(name, "reply-failed") || !strcmp(name, "reply-ready-custom-token") ||
             !strcmp(name, "isp-matched") || !strcmp(name, "isp-failed") || !strcmp(name, "isp-unknown") ||
             !strcmp(name, "isp-pinhole") || needs_terminal)
        mode = ART_REPLY_MODE;
    else if (!strcmp(name, "neutral") || !strcmp(name, "pinhole")) mode = 2;
    else if (!strcmp(name, "allocate") || !strcmp(name, "existing") ||
             !strcmp(name, "failed") || !strcmp(name, "cropped")) mode = 1;
    else return 2;
    FILE *f = fopen(argv[1], "rb");
    image = malloc(IMAGE_BYTES);
    if (!f || !image || fread(image, 1, IMAGE_BYTES, f) != IMAGE_BYTES || fgetc(f) != EOF) return 2;
    fclose(f);
    if (needs_terminal) {
        FILE *terminal = fopen(argv[3], "rb");
        if (!terminal) return 2;
        const size_t bytes = fread(stack_ram + (ART_TERMINAL_FIXTURE - STACK), 1,
                                   ART_TERMINAL_MAX_BYTES, terminal);
        const int valid = bytes && fgetc(terminal) == EOF && !ferror(terminal);
        fclose(terminal);
        if (!valid) return 2;
    }
    if (mode == CHROMA_MODE) {
        int result = probe_chroma();
        free(image);
        return result;
    }
    if (mode == ART_REPLY_MODE) {
        int result = probe_art_reply(name);
        free(image);
        return result;
    }
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
