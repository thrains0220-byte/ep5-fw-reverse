/* SPDX-License-Identifier: GPL-3.0-or-later
 * Mode 3 full chain on the CPU model: one stock ART send, receive tail, JPEG
 * caller and release fragment execute the cave veneers and the SD look loader.
 * The file service and ART memory pool are modeled backends fed with real
 * desktop pack bytes; no filesystem, ISP, scheduler or camera I/O. */
#include "emu.h"

#define BASE 0x7e101020u
#define IMAGE_BYTES 15728576u
#define CAVE 0x7e128010u
#define CAVE_BYTES 32752u
#define UNCAVE (CAVE + 0x40000000u)
#define HOOK 0x7e3ed8d1u
#define CODEC 0x7e3f4884u
#define LOGGER 0x7e3f0464u
#define WAIT_HOOK 0x7e3ed850u
#define RECEIVER 0x7e3f7fa7u
#define RELEASE_HOOK 0x7e3f2476u
#define PARAM_HOOK 0x7e3ed835u
#define PARAM_CONTINUE 0x7e3ed83cu
#define SEND 0x7e3fca97u
#define QUEUE_READ 0x7e117c7cu
#define QUEUE_ROUTE 0x7e132fdeu
#define QUEUE_ERROR 0x7e132ed3u
#define ERROR_LOG 0x7e106c9du
#define FREE_BUFFER 0x7e23e0b0u
#define POOL_ALLOC 0x7e23e0ffu
#define POOL_FREE 0x7e23e2fdu
#define FILE_SELECT 0x7e2914f1u
#define FILE_OPEN 0x7e2960dbu
#define FILE_READ 0x7e296da5u
#define FILE_CLOSE 0x7e29640eu
#define FILE_MSG 0x7e13452bu
#define SEND_CHECK 0x7e3fd443u
#define SEND_CHECK2 0x7e3fd45cu
#define SEND_PACK 0x7e3fd94au
#define SEND_RING 0x7e3fd922u
#define SEND_QUEUE 0x7e3fd6d2u
#define STACK 0x60000000u
#define CALLER (STACK + 0x100u)
#define CONTEXT 0x11000000u
#define SETTINGS (CONTEXT + 0x100u)
#define PIXELS 0x12000000u
#define POOL (PIXELS + 0x10000u)
#define POOL_BYTES 58956u
#define POOL_STATUS 0xa087c9dcu
#define ART_GLOBAL 0x605f455cu
#define PACKET 0x605f4510u
#define HANDLE 0x125af004u
#define LUT_VALUES 14739u

/* Settings live at CONTEXT+0x100 and reach offset 18147; the buffer must
 * cover the whole settings region, not just the old 0x4600 window. */
static uint8_t *image, stack_ram[65536], context[0x5000], globals[16];
static uint8_t pixels[65536], pool_ram[POOL_BYTES], packet[396];
static uint8_t pool_status[8];
static uint32_t pixel_bytes;
static uint8_t rec_return[8] = {0xdf, 0xa0, 12}, codec_return[8] = {0xdf, 0xf0, 16};
static uint8_t queue_return[8] = {0xdf, 0xf0, 32}, route_return[8] = {0xdf, 0xc0, 16};
static uint8_t error_return[8] = {0xdf, 0xf0, 124}, error_log_return[8] = {0xdf, 0xa0, 40};
static uint8_t free_return[8] = {0xdf, 0x00, 4};
static uint8_t send_return[8] = {0xdf, 0xa0, 20};
static uint8_t squeue_return[8] = {0xdf, 0xf0, 16};
static uint8_t select_return[8] = {0xdf, 0, 8};
static uint8_t fopen_return[8] = {0xdf, 0xf0, 64}, fread_return[8] = {0xdf, 0xf0, 20};
static uint8_t fclose_return[8] = {0xdf, 0xb0, 16}, fmsg_return[8] = {0xdf, 0xc0, 12};

static uint32_t bridge_call, wait_call, param_call, state_offset, look_state_offset;
static uint32_t control_offset_global;
static uint32_t registers_at_hook[8], mdr_at_hook, sp_at_hook, request[10];
static unsigned hook_count, codec_calls, bridge_count;
static uint32_t wait_registers[8], wait_sp, returned_registers[8], returned_mdr;
static unsigned wait_calls, release_calls, state_writes;
static int wait_preserved = 1, wait_return_preserved = 1, arguments_preserved = 1;
static int reached_stop;
static uint32_t param_registers[8], param_sp;
static unsigned send_calls;
static int param_preserved = 1, send_envelope_valid = 1;

/* Synthetic filesystem: two named files, one live handle, sequential reads. */
static uint8_t index_data[2048], lut_data[40000];
static unsigned index_len, lut_len;
static int have_index, have_lut, direct_backend = 1, pool_fail;
static int opened, read_calls, closed, live; /* live: 0 none, 1 index, 2 lut */
static unsigned live_pos;
static unsigned pool_allocs, pool_frees;
static uint32_t dbg_exact, dbg_lookread, dbg_load, dbg_loadret;
static uint32_t state_aw_pc, state_bj_pc, state_ap_pc;
static int pool_live;
static uint8_t config[72];
uint64_t emu_ns;

static int within(uint32_t a, uint32_t n, uint32_t b, uint32_t bytes)
{ return a >= b && (uint64_t)a + n <= (uint64_t)b + bytes; }

uint8_t *mem_host(uint32_t a, uint32_t n)
{
    if (within(a, n, LOGGER, 8)) return rec_return + (a - LOGGER);
    if (within(a, n, CODEC, 8)) return codec_return + (a - CODEC);
    if (within(a, n, QUEUE_READ, 8)) return queue_return + (a - QUEUE_READ);
    if (within(a, n, QUEUE_ROUTE, 8)) return route_return + (a - QUEUE_ROUTE);
    if (within(a, n, QUEUE_ERROR, 8)) return error_return + (a - QUEUE_ERROR);
    if (within(a, n, ERROR_LOG, 8)) return error_log_return + (a - ERROR_LOG);
    if (within(a, n, FREE_BUFFER, 8)) return free_return + (a - FREE_BUFFER);
    if (within(a, n, SEND, 8)) return send_return + (a - SEND);
    if (within(a, n, SEND_QUEUE, 8)) return squeue_return + (a - SEND_QUEUE);
    if (within(a, n, FILE_SELECT, 8)) return select_return + (a - FILE_SELECT);
    if (within(a, n, FILE_OPEN, 8)) return fopen_return + (a - FILE_OPEN);
    if (within(a, n, FILE_READ, 8)) return fread_return + (a - FILE_READ);
    if (within(a, n, FILE_CLOSE, 8)) return fclose_return + (a - FILE_CLOSE);
    if (within(a, n, FILE_MSG, 8)) return fmsg_return + (a - FILE_MSG);
    if (within(a, n, BASE, IMAGE_BYTES)) return image + (a - BASE);
    if (within(a, n, STACK, sizeof stack_ram)) return stack_ram + (a - STACK);
    if (within(a, n, STACK + 0x40000000u, sizeof stack_ram)) return stack_ram + (a - STACK - 0x40000000u);
    if (within(a, n, CONTEXT, sizeof context)) return context + (a - CONTEXT);
    /* Only the 4-byte buffer-pointer global: a wider window would alias
     * packet[76..92] and swallow the ART neutralization writes. */
    if (within(a, n, ART_GLOBAL, 4)) return globals + (a - ART_GLOBAL);
    if (within(a, n, PACKET, sizeof packet)) return packet + (a - PACKET);
    if (within(a, n, PIXELS, pixel_bytes)) return pixels + (a - PIXELS);
    if (within(a, n, POOL, sizeof pool_ram)) return pool_ram + (a - POOL);
    if (within(a, n, POOL_STATUS, sizeof pool_status)) return pool_status + (a - POOL_STATUS);
    if (within(a, n, UNCAVE, CAVE_BYTES)) return image + (CAVE - BASE) + (a - UNCAVE);
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
    if (!within(a, (uint32_t)n, STACK, sizeof stack_ram) &&
        !within(a, (uint32_t)n, STACK + 0x40000000u, sizeof stack_ram) &&
        !within(a, (uint32_t)n, PIXELS, pixel_bytes) &&
        !within(a, (uint32_t)n, POOL, sizeof pool_ram) &&
        !within(a, (uint32_t)n, PACKET, sizeof packet) &&
        !within(a, (uint32_t)n, ART_GLOBAL, 4) &&
        !within(a, (uint32_t)n, UNCAVE + state_offset, 24))
        emu_abort(PC, "write outside model %08x", a);
    uint8_t *p = mem_host(a, (uint32_t)n);
    if (within(a, (uint32_t)n, UNCAVE + state_offset, 8)) ++state_writes;
    for (int i = 0; i < n; ++i) p[i] = (uint8_t)(v >> (8 * i));
}

void mem_misaligned(uint32_t a, int n, int wr) { emu_abort(PC, "misaligned %08x/%d/%d", a, n, wr); }
void soc_tick(uint64_t cycles) { emu_ns += cycles; }
uint64_t soc_next_event(void) { return emu_ns + 1; }

static uint32_t word(const uint8_t *p)
{ return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static void put(uint8_t *p, uint32_t v)
{ for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(v >> (8 * i)); }
static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }

/* call [regs],N stores the return address at the caller SP and enters the
 * callee at SP-N; a modeled ret [],N / retf [],N must place it back at SP+N. */
static void fixret(cpu_t *cpu, uint32_t n)
{ mem_wr(cpu->regs[REG_SP] + n, cpu->regs[REG_MDR], 4); }

static int path_is(uint32_t a, const char *s)
{
    for (unsigned i = 0; s[i]; ++i) if (mem_rd(a + i, 1) != (uint8_t)s[i]) return 0;
    return mem_rd(a + strlen(s), 1) == 0;
}

/* One file operation, shared by the direct and message backends. */
static uint32_t file_open(uint32_t path, uint32_t mode)
{
    if (live || !path_is(mode, "rb")) {
        fprintf(stderr, "open: live=%d path=%08x mode=%08x modebytes=", live, path, mode);
        for (unsigned i = 0; i < 4; ++i) fprintf(stderr, "%02x ", mem_rd(mode + i, 1));
        fprintf(stderr, " pathbytes=");
        for (unsigned i = 0; i < 20; ++i) { uint8_t c = (uint8_t)mem_rd(path + i, 1); fprintf(stderr, "%c", c >= 32 && c < 127 ? c : '.'); if (!c) break; }
        fprintf(stderr, "\n");
        emu_abort(PC, "bad open state/mode");
    }
    ++opened;
    if (path_is(path, "EP5LUT/INDEX.EP5") && have_index) { live = 1; live_pos = 0; return HANDLE; }
    if (path_is(path, "EP5LUT/L0000001.LUT") && have_lut) { live = 2; live_pos = 0; return HANDLE; }
    return 0;
}
static uint32_t file_read(uint32_t dst, uint32_t size, uint32_t count, uint32_t handle)
{
    if (!live || handle != HANDLE || size != 1) emu_abort(PC, "bad read state");
    ++read_calls;
    const uint8_t *data = live == 1 ? index_data : lut_data;
    unsigned len = live == 1 ? index_len : lut_len;
    unsigned n = count;
    if (live_pos + n > len) n = len - live_pos;
    for (unsigned i = 0; i < n; ++i) mem_wr(dst + i, data[live_pos + i], 1);
    live_pos += n;
    return n;
}
static uint32_t file_close(uint32_t handle)
{
    if (!live || handle != HANDLE) emu_abort(PC, "bad close state");
    ++closed; live = 0; return 0;
}

int hle_is_hook(uint32_t a)
{
    return a == HOOK || a == bridge_call || a == CODEC || a == LOGGER ||
           a == WAIT_HOOK || a == RECEIVER || a == CALLER + 7 ||
           a == PARAM_CONTINUE || a == 0x7e3ed857 || a == FREE_BUFFER ||
           a == 0x7e3f247b || a == QUEUE_READ || a == QUEUE_ROUTE ||
           a == wait_call + 7 || a == SEND || a == SEND_CHECK || a == SEND_PACK ||
           a == SEND_CHECK2 || a == SEND_RING || a == SEND_QUEUE || a == FILE_SELECT || a == FILE_OPEN ||
           a == FILE_READ || a == FILE_CLOSE || a == FILE_MSG ||
           a == POOL_ALLOC || a == POOL_FREE || a == 0x7e40a3fc || a == 0x7e12818b || a == 0x7e40a43f ||
           a == 0x7e291524 || a == 0x7e291554 || a == 0x7e291515 || a == 0x7e128155 || a == 0x7e12815c ||
           (a >= CAVE && a < CAVE + CAVE_BYTES && (getenv("EP5_TRACE") || getenv("EP5_STATE")));
}

int hle_check(cpu_t *cpu)
{
    uint32_t pc = cpu->regs[REG_PC];
    uint32_t *r = cpu->regs;
    if (pc == CALLER + 7 || pc == 0x7e3f247b) { reached_stop = emu_stop = 1; return 1; }

    /* ---- stock send internals (modeled sinks) ---- */
    if (pc == SEND) {
        ++send_calls;
        /* The veneer saves d2/a2 below the caller frame; the other registers
         * and the envelope must arrive unchanged. */
        for (unsigned i = 0; i < 8; ++i)
            if (i != REG_D0 + 2 && i != REG_A0 + 2)
                param_preserved &= r[i] == param_registers[i];
        param_preserved &= r[REG_D0 + 2] == param_registers[REG_D0 + 2] &&
                           r[REG_A0 + 2] == param_registers[REG_A0 + 2];
        /* Measured on the pinned CPU model: at the send sink the callee SP
         * is exactly 20 below the stock SP (the veneer restores its frame
         * before the call; only the call frame remains). */
        if (r[REG_SP] != param_sp - 20 || r[REG_MDR] != param_call + 7) {
            param_preserved = 0;
            fprintf(stderr, "send frame: sp=%x want %x mdr=%x want %x\n",
                    r[REG_SP], param_sp - 20, r[REG_MDR], param_call + 7);
        }
        send_envelope_valid &= r[REG_A0] == param_sp + 4 &&
            mem_rd(r[REG_A0], 4) == 0x123u && mem_rd(r[REG_A0] + 4, 4) == 1 &&
            mem_rd(r[REG_A0] + 8, 4) == 1 && mem_rd(r[REG_A0] + 12, 4) == param_registers[REG_A0 + 2];
        if (!send_envelope_valid)
            fprintf(stderr, "envelope: a0=%x want %x [%x %x %x %x] a2=%x\n",
                    r[REG_A0], param_sp + 4, mem_rd(r[REG_A0], 4), mem_rd(r[REG_A0] + 4, 4),
                    mem_rd(r[REG_A0] + 8, 4), mem_rd(r[REG_A0] + 12, 4), param_registers[REG_A0 + 2]);
        r[REG_D0] = 0x2345;
        /* Execute the veneer's real return instruction: the stock send frame
         * is ret [d2,a2],20, which restores the saved registers and returns
         * to the MDR fixup, then PARAM_CONTINUE. Never stop at the sink. */
        return 0;
    }
    if (pc == PARAM_CONTINUE) {
        /* Full preservation is only required after the veneer restored its
         * saved registers and fixed MDR back to the stock continuation. */
        for (unsigned i = 0; i < 8; ++i)
            if (i != REG_D0) param_preserved &= r[i] == param_registers[i];
        param_preserved &= r[REG_D0] == 0x2345;
        param_preserved &= r[REG_SP] == param_sp && r[REG_MDR] == PARAM_CONTINUE;
        reached_stop = emu_stop = 1;
        return 1;
    }
    /* Shared debug/log helpers execute as patched clean returns; their return
     * addresses land above the pool mode/line, leaving them intact. */
    if (pc == SEND_CHECK || pc == SEND_CHECK2 || pc == SEND_PACK || pc == SEND_RING) return 0;
    if (pc == 0x7e40a3fc && getenv("EP5_TRACE"))
    {
        fprintf(stderr, "ABA_ENTRY sp=%x:", r[REG_SP]);
        for (int o = -16; o <= 52; o += 4) fprintf(stderr, " [%d]=%x", o, mem_rd(r[REG_SP] + o, 4));
        fprintf(stderr, "\n");
    }
    if (pc == 0x7e12818b && getenv("EP5_TRACE"))
    {
        fprintf(stderr, "VENEER sp=%x:", r[REG_SP]);
        for (int o = -8; o <= 60; o += 4) fprintf(stderr, " [%d]=%x", o, mem_rd(r[REG_SP] + o, 4));
        fprintf(stderr, "\n");
    }
    if (pc == 0x7e40a43f && getenv("EP5_TRACE"))
    {
        fprintf(stderr, "ABA_AFTER_MOVHU sp=%x d2(mode)=%x [36sp]=%x\n",
                r[REG_SP], r[REG_D0 + 2], mem_rd(r[REG_SP] + 36, 4));
    }
    if (pc >= CAVE && pc < CAVE + CAVE_BYTES && getenv("EP5_TRACE")) {
        if (getenv("EP5_DBG_ALL") || pc == dbg_exact || pc == dbg_lookread || pc == dbg_load || pc == dbg_loadret) {
            fprintf(stderr, "DBG %x sp=%x d0=%x d1=%x a0=%x a1=%x mdr=%x:",
                    pc, r[REG_SP], r[REG_D0], r[REG_D0 + 1], r[REG_A0], r[REG_A0 + 1], r[REG_MDR]);
            for (int o = 0; o <= 44; o += 4) fprintf(stderr, " [%d]=%x", o, mem_rd(r[REG_SP] + o, 4));
            fprintf(stderr, " d2=%x d3=%x a2=%x a3=%x", r[REG_D0 + 2], r[REG_D0 + 3], r[REG_A0 + 2], r[REG_A0 + 3]);
            fprintf(stderr, "\n");
            fflush(stderr);
        }
    }
    if (getenv("EP5_STATE") && (pc == state_aw_pc || pc == state_bj_pc)) {
        /* after_wait / before_jpeg entry: dump the qualification state. */
        fprintf(stderr, "STATE pc=%x ready=[%x,%x] look=[%x,%x,%x,%x] ctrl1=%x\n",
                pc,
                mem_rd(UNCAVE + state_offset, 4), mem_rd(UNCAVE + state_offset + 4, 4),
                mem_rd(UNCAVE + look_state_offset, 4), mem_rd(UNCAVE + look_state_offset + 4, 4),
                mem_rd(UNCAVE + look_state_offset + 8, 4), mem_rd(UNCAVE + look_state_offset + 12, 4),
                mem_rd(CAVE + control_offset_global, 4));
        if (pc == state_bj_pc) {
            /* before_jpeg(request=d0, context=d1): dump the raw 40-byte request. */
            uint32_t rq = r[REG_D0];
            fprintf(stderr, "  REQ@%x:", rq);
            for (int o = 0; o < 40; o += 4) fprintf(stderr, " [%d]=%08x", o, mem_rd(rq + o, 4));
            fprintf(stderr, "\n");
        }
        fflush(stderr);
    }
    if (getenv("EP5_STATE") && pc == state_ap_pc) {
        /* film_apply callsite: a0=d0=image struct at sp+52; d1=table. */
        uint32_t img = r[REG_A0];
        fprintf(stderr, "APPLY pc=%x img=%x data=%x cap=%x w=%x h=%x stride=%x table=%x values=%x enc=%x amount=%x\n",
                pc, img,
                mem_rd(img, 4), mem_rd(img + 4, 4), mem_rd(img + 8, 4),
                mem_rd(img + 12, 4), mem_rd(img + 16, 4),
                r[REG_D0 + 1], mem_rd(r[REG_SP] + 12, 4), mem_rd(r[REG_SP] + 16, 4),
                mem_rd(r[REG_SP] + 20, 4));
        fprintf(stderr, "  pix0=%02x%02x%02x%02x pix4=%02x%02x%02x%02x\n",
                pixels[0], pixels[1], pixels[2], pixels[3],
                pixels[4], pixels[5], pixels[6], pixels[7]);
        fflush(stderr);
    }
    if (pc == SEND_QUEUE) { fixret(cpu, 16); r[REG_D0] = 0; return 1; }

    /* ---- file backend selection and operations ---- */
    /* Like the proven file probe: substitute only the backend result and
     * execute each target's real frame-return instruction (fixret would
     * double-apply the frame and skip the wrapper's own epilogue). */
    if (pc == FILE_SELECT) { r[REG_D0] = (uint32_t)direct_backend; return 0; }
    if (pc == FILE_OPEN) { if (!direct_backend) emu_abort(pc, "direct open in message mode"); r[REG_A0] = file_open(r[REG_A0], r[REG_A0 + 1]); return 0; }
    if (pc == 0x7e291524 && getenv("EP5_TRACE"))
        fprintf(stderr, "OPEN_CALL sp=%x ret_slot=%x mdr=%x\n", r[REG_SP], mem_rd(r[REG_SP],4), r[REG_MDR]);
    if (pc == 0x7e291554 && getenv("EP5_TRACE"))
        fprintf(stderr, "OPEN_RET sp=%x a0=%x [sp]=%x\n", r[REG_SP], r[REG_A0], mem_rd(r[REG_SP],4));
    if (pc == 0x7e291515 && getenv("EP5_TRACE"))
        fprintf(stderr, "STOCK_OPEN_ENTRY sp=%x [sp]=%x [sp+4]=%x [sp+8]=%x mdr=%x\n",
                r[REG_SP], mem_rd(r[REG_SP],4), mem_rd(r[REG_SP]+4,4), mem_rd(r[REG_SP]+8,4), r[REG_MDR]);
    if (pc == 0x7e128155 && getenv("EP5_TRACE"))
        fprintf(stderr, "VENEER_CALL_PRE sp=%x [sp]=%x mdr=%x\n", r[REG_SP], mem_rd(r[REG_SP],4), r[REG_MDR]);
    if (pc == 0x7e12815c && getenv("EP5_TRACE"))
        fprintf(stderr, "VENEER_RET_PRE sp=%x [sp]=%x a0=%x mdr=%x\n", r[REG_SP], mem_rd(r[REG_SP],4), r[REG_A0], r[REG_MDR]);
    if (pc == 0x7e12815c && getenv("EP5_STEP")) {
        fprintf(stderr, "RET_INSN sp=%x [sp]=%x [sp-4]=%x [sp+4]=%x\n",
                r[REG_SP], mem_rd(r[REG_SP],4), mem_rd(r[REG_SP]-4,4), mem_rd(r[REG_SP]+4,4));
    }
    if (pc == FILE_READ) {
        if (!direct_backend) emu_abort(pc, "direct read in message mode");
        if (getenv("EP5_TRACE")) {
            fprintf(stderr, "READ_HOOK sp=%x dst=%x size=%x count=%x file=%x live=%u\n",
                    r[REG_SP], r[REG_A0], r[REG_D0], r[REG_D0 + 1], r[REG_A0 + 1], live);
            fprintf(stderr, "  d2=%x d3=%x a2=%x a3=%x mdr=%x\n",
                    r[REG_D0 + 2], r[REG_D0 + 3], r[REG_A0 + 2], r[REG_A0 + 3], r[REG_MDR]);
        }
        r[REG_D0] = file_read(r[REG_A0], r[REG_D0], r[REG_D0 + 1], r[REG_A0 + 1]);
        return 0;
    }
    if (pc == FILE_CLOSE) { if (!direct_backend) emu_abort(pc, "direct close in message mode"); r[REG_D0] = file_close(r[REG_A0]); return 0; }
    if (pc == FILE_MSG) {
        if (direct_backend || r[REG_D0] != 0x22) emu_abort(pc, "bad file message service");
        uint32_t a = r[REG_A0];
        switch (r[REG_D0 + 1]) {
        case 0x10001: mem_wr(a, file_open(mem_rd(a + 4, 4), mem_rd(a + 8, 4)), 4); break;
        case 0x10005: mem_wr(a, file_read(mem_rd(a + 4, 4), mem_rd(a + 8, 4), mem_rd(a + 12, 4), mem_rd(a + 16, 4)), 4); break;
        case 0x10002: mem_wr(a, file_close(mem_rd(a + 4, 4)), 4); break;
        default: emu_abort(pc, "unexpected file message %x", r[REG_D0 + 1]);
        }
        r[REG_D0] = 0;
        return 0;
    }

    /* ---- ART memory pool backends ---- */
    if (pc == POOL_ALLOC) {
        ++pool_allocs;
        if (pool_fail || pool_live) r[REG_D0] = 0;
        else { pool_live = 1; r[REG_D0] = POOL; }
        return 0;
    }
    if (pc == POOL_FREE) {
        if (!pool_live || r[REG_D0] != POOL) emu_abort(pc, "bad pool free");
        ++pool_frees; pool_live = 0;
        return 0;
    }

    /* ---- receive tail ---- */
    if (pc == WAIT_HOOK) {
        memcpy(wait_registers, r, sizeof wait_registers);
        wait_sp = r[REG_SP];
        uint32_t reply = r[REG_A0];
        mem_wr(reply, 0, 4); mem_wr(reply + 4, 1, 4); mem_wr(reply + 8, PACKET, 4);
    }
    if (pc == RECEIVER) {
        for (unsigned i = 0; i < 8; ++i) wait_preserved &= wait_registers[i] == r[i];
        wait_preserved &= r[REG_SP] == wait_sp - 32 && r[REG_MDR] == wait_call + 7;
        uint32_t p = r[REG_A0];
        if (!within(p, 12, STACK, sizeof stack_ram) || r[REG_D0] != 0x123 ||
            r[REG_D0 + 1] != 12 || r[REG_A0 + 1] != 0xffffffff)
            emu_abort(pc, "bad original receive arguments");
    }
    if (pc == QUEUE_ROUTE) r[REG_D0] = 0;
    if (pc == QUEUE_READ) {
        uint32_t p = r[REG_A0];
        if (!within(p, 12, STACK, sizeof stack_ram) || r[REG_D0] != 0x123 ||
            r[REG_D0 + 1] != 0xffffffff)
            emu_abort(pc, "bad native kernel queue arguments");
        int32_t received = (int32_t)word(config + 44);
        if (received >= 0) {
            unsigned n = received < 12 ? (unsigned)received : 12;
            for (unsigned i = 0; i < n; ++i) mem_wr(p + i, config[48 + i], 1);
        }
        r[REG_D0] = (uint32_t)received;
        r[REG_D0 + 1] = 0xaced;
        r[REG_A0] = 0x10203040;
        r[REG_A0 + 1] = 0x50607080;
        ++wait_calls;
    }
    if (pc == wait_call + 7) {
        memcpy(returned_registers, r, sizeof returned_registers);
        returned_mdr = r[REG_MDR];
        int32_t k = (int32_t)word(config + 44);
        uint32_t result = k == -50 ? 0xfffffffeu : k < 0 ? 0xffffffffu : 0;
        if (r[REG_D0] != result) emu_abort(pc, "unexpected queue wrapper result");
    }
    if (pc == 0x7e3ed857) {
        for (unsigned i = 0; i < 8; ++i) wait_return_preserved &= r[i] == returned_registers[i];
        wait_return_preserved &= r[REG_SP] == wait_sp && r[REG_MDR] == returned_mdr;
    }

    /* ---- release / free ---- */
    if (pc == FREE_BUFFER) {
        /* 0x7e23e0b0 is the shared low-level free: the ART pool block frees
         * through it (D0=POOL) as does the stock image buffer (D0=base). */
        if (r[REG_D0] == POOL) {
            if (!pool_live) emu_abort(pc, "pool free without live block");
            ++pool_frees; pool_live = 0;
        } else if (r[REG_D0] == word(config + 40)) {
            if (mem_rd(UNCAVE + state_offset, 4) || mem_rd(UNCAVE + state_offset + 4, 4))
                emu_abort(pc, "qualification survived release");
            ++release_calls;
        } else {
            emu_abort(pc, "incorrect native free argument");
        }
    }

    /* ---- JPEG caller ---- */
    if (pc == HOOK) {
        for (unsigned i = 0; i < 8; ++i) registers_at_hook[i] = r[i];
        mdr_at_hook = r[REG_MDR];
        sp_at_hook = r[REG_SP];
        uint32_t p = r[REG_A0 + 1];
        if (!within(p, 40, STACK, sizeof stack_ram)) emu_abort(pc, "invalid original request");
        for (unsigned i = 0; i < 10; ++i) request[i] = mem_rd(p + 4 * i, 4);
        ++hook_count;
    }
    if (pc == bridge_call || pc == CODEC) {
        if (hook_count != codec_calls + 1) emu_abort(pc, "native codec without unique entry");
        for (unsigned i = 0; i < 8; ++i)
            arguments_preserved &= registers_at_hook[i] == r[i];
        uint32_t expected_mdr = pc == bridge_call ? mdr_at_hook : bridge_call + 7;
        uint32_t expected_sp = pc == bridge_call ? sp_at_hook : sp_at_hook - 16;
        arguments_preserved &= expected_mdr == r[REG_MDR] && expected_sp == r[REG_SP];
        uint32_t p = r[REG_A0 + 1];
        for (unsigned i = 0; i < 10; ++i) arguments_preserved &= request[i] == mem_rd(p + 4 * i, 4);
        if (pc == CODEC) { ++codec_calls; r[REG_D0] = 0x1234; }
        else ++bridge_count;
    }
    return 0;
}

static size_t load(const char *name, uint8_t *p, size_t capacity)
{
    FILE *f = fopen(name, "rb");
    if (!f) { perror(name); exit(2); }
    size_t count = fread(p, 1, capacity, f);
    if (ferror(f) || fgetc(f) != EOF) { fprintf(stderr, "input exceeds bounds\n"); exit(2); }
    fclose(f);
    return count;
}

static void reset_regs(void)
{
    reached_stop = emu_stop = 0;
    for (unsigned i = 0; i < 8; ++i) cpus[0].regs[i] = 0xabcd1000u + i;
    cpus[0].regs[REG_A0] = CONTEXT;
    cpus[0].regs[REG_PC] = CALLER;
    cpus[0].regs[REG_SP] = STACK + 0xf000;
    cpus[0].regs[REG_MDR] = 0x13579bdf;
}

int main(int argc, char **argv)
{
    if (argc != 18) return 2;
    uint8_t payload[CAVE_BYTES];
    image = malloc(IMAGE_BYTES);
    if (!image || load(argv[1], image, IMAGE_BYTES) != IMAGE_BYTES || load(argv[3], config, 72) != 72) return 2;
    size_t payload_bytes = load(argv[2], payload, CAVE_BYTES);
    char *tail;
    unsigned long control_offset = strtoul(argv[6], &tail, 10);
    if (*tail || !payload_bytes || payload_bytes < 28 || control_offset > payload_bytes - 28 || (control_offset & 3)) return 2;
    control_offset_global = (uint32_t)control_offset;
    unsigned long call_offset = strtoul(argv[7], &tail, 10);
    if (*tail || call_offset > payload_bytes - 7 || payload[call_offset] != 0xdd ||
        payload[call_offset + 5] != 0xf0 || payload[call_offset + 6] != 16) return 2;
    bridge_call = CAVE + (uint32_t)call_offset;
    unsigned long state = strtoul(argv[8], &tail, 10);
    if (*tail || state > payload_bytes - 24 || (state & 3)) return 2;
    state_offset = (uint32_t)state;
    unsigned long wait_entry = strtoul(argv[9], &tail, 10);
    if (*tail || wait_entry >= payload_bytes) return 2;
    unsigned long wait_offset = strtoul(argv[10], &tail, 10);
    if (*tail || wait_offset > payload_bytes - 7 || payload[wait_offset] != 0xdd ||
        payload[wait_offset + 5] != 0 || payload[wait_offset + 6] != 20) return 2;
    wait_call = CAVE + (uint32_t)wait_offset;
    unsigned long release_entry = strtoul(argv[11], &tail, 10);
    if (*tail || release_entry >= payload_bytes) return 2;
    unsigned long param_entry = strtoul(argv[12], &tail, 10);
    if (*tail || param_entry >= payload_bytes) return 2;
    unsigned long param_offset = strtoul(argv[13], &tail, 10);
    if (*tail || param_offset > payload_bytes - 7 || payload[param_offset] != 0xdd ||
        payload[param_offset + 5] != 0xa0 || payload[param_offset + 6] != 20) return 2;
    param_call = CAVE + (uint32_t)param_offset;
    unsigned long look_state = strtoul(argv[14], &tail, 10);
    if (*tail || look_state > payload_bytes - 16 || (look_state & 3)) return 2;
    look_state_offset = (uint32_t)look_state;
    const char *scenario = argv[15];
    direct_backend = atoi(argv[16]);
    const char *card_dir = argv[17];
    /* Optional symbol-driven debug PCs: EP5_DBG="exact,lookread,load,loadret"
     * as hex cave offsets, resolved by the caller from the module symbols. */
    if (getenv("EP5_DBG")) {
        unsigned long v[4] = {0, 0, 0, 0};
        sscanf(getenv("EP5_DBG"), "%lx,%lx,%lx,%lx", &v[0], &v[1], &v[2], &v[3]);
        dbg_exact = v[0] ? CAVE + (uint32_t)v[0] : 0;
        dbg_lookread = v[1] ? CAVE + (uint32_t)v[1] : 0;
        dbg_load = v[2] ? CAVE + (uint32_t)v[2] : 0;
        dbg_loadret = v[3] ? CAVE + (uint32_t)v[3] : 0;
    }
    if (getenv("EP5_STATE_PC")) {
        unsigned long aw = 0, bj = 0, ap = 0;
        sscanf(getenv("EP5_STATE_PC"), "%lx,%lx,%lx", &aw, &bj, &ap);
        state_aw_pc = aw ? CAVE + (uint32_t)aw : 0;
        state_bj_pc = bj ? CAVE + (uint32_t)bj : 0;
        state_ap_pc = ap ? CAVE + (uint32_t)ap : 0;
    }

    /* Load synthetic card files; absent file means the loader must fall back. */
    char path[512];
    snprintf(path, sizeof path, "%s/INDEX.EP5", card_dir);
    FILE *f = fopen(path, "rb");
    if (f) { index_len = (unsigned)fread(index_data, 1, sizeof index_data, f); have_index = 1; fclose(f); }
    snprintf(path, sizeof path, "%s/L0000001.LUT", card_dir);
    f = fopen(path, "rb");
    if (f) { lut_len = (unsigned)fread(lut_data, 1, sizeof lut_data, f); have_lut = 1; fclose(f); }
    pool_fail = !strcmp(scenario, "pool_fail");

    const uint8_t expected[] = {0xcd, 0xb3, 0x6f, 0xf0, 0x10};
    if (memcmp(image + (HOOK - BASE), expected, 5)) return 2;
    const uint8_t expected_wait[] = {0xdd, 0x57, 0xa7, 0, 0, 0, 20};
    if (memcmp(image + (WAIT_HOOK - BASE), expected_wait, 7)) return 2;
    const uint8_t expected_release[] = {0xcd, 0x4b, 0xb6, 0, 4};
    if (memcmp(image + (RELEASE_HOOK - BASE), expected_release, 5)) return 2;
    const uint8_t expected_param[] = {0xdd, 0x62, 0xf2, 0, 0, 0xa0, 20};
    if (memcmp(image + (PARAM_HOOK - BASE), expected_param, 7)) return 2;
    for (unsigned i = 0; i < CAVE_BYTES; ++i) if (image[CAVE - BASE + i] != 255) return 2;
    memcpy(payload + control_offset, config, 28);
    memcpy(image + (CAVE - BASE), payload, payload_bytes);
    image[HOOK - BASE] = 0xdc; put(image + (HOOK - BASE) + 1, CAVE - HOOK);
    image[WAIT_HOOK - BASE] = 0xdc; put(image + (WAIT_HOOK - BASE) + 1, CAVE + (uint32_t)wait_entry - WAIT_HOOK);
    image[WAIT_HOOK - BASE + 5] = image[WAIT_HOOK - BASE + 6] = 0xcb;
    image[RELEASE_HOOK - BASE] = 0xdc; put(image + (RELEASE_HOOK - BASE) + 1, CAVE + (uint32_t)release_entry - RELEASE_HOOK);
    image[PARAM_HOOK - BASE] = 0xdc; put(image + (PARAM_HOOK - BASE) + 1, CAVE + (uint32_t)param_entry - PARAM_HOOK);
    image[PARAM_HOOK - BASE + 5] = image[PARAM_HOOK - BASE + 6] = 0xcb;
    /* Model the ART pool at its lowest backend; the real wrappers and the
     * intermediate frames execute, as in the proven pixel probe. */
    memcpy(image + (POOL_ALLOC - BASE), "\xdf\x00\x50", 3);
    memcpy(image + (POOL_FREE - BASE), "\xdf\x00\x2c", 3);
    memcpy(image + (SEND_CHECK - BASE), "\xdf\x00\x04", 3);
    memcpy(image + (SEND_CHECK2 - BASE), "\xdf\x20\x08", 3);
    memcpy(image + (SEND_PACK - BASE), "\xdf\x00\x00", 3);
    memcpy(image + (SEND_RING - BASE), "\xdf\x80\x04", 3);

    pixel_bytes = (uint32_t)load(argv[4], pixels, sizeof pixels);
    if (!pixel_bytes) return 2;
    put(context + 84, SETTINGS);
    context[0x100 + 17454] = (uint8_t)word(config + 36);
    context[0x100 + 17471] = (uint8_t)word(config + 28);      /* PictureMode */
    context[0x100 + 18147] = (uint8_t)word(config + 32);      /* variant */
    put16(context + 0x100 + 17442, 0);                        /* source */
    put(globals, word(config + 40));
    memcpy(globals + 4, config + 28, 8);
    /* Stock pre-send packet: pin-hole filter 73 with extra colour fields set. */
    put16(packet, 1); put16(packet + 2, 3); put16(packet + 6, 73);
    packet[96] = 1;
    for (unsigned i = 80; i <= 90; ++i) packet[i] = (uint8_t)(i + 1);
    packet[157] = 0;

    uint8_t *caller = stack_ram + (CALLER - STACK);
    caller[0] = 0xdd; caller[5] = 0xb0; caller[7] = 0xcb;
    cpus[0].running = 1;
    cpus[0].irq_level = 7;

    /* ---- phase A: stock send through the param veneer (look_prepare) ---- */
    put(caller + 1, PARAM_HOOK - CALLER);
    caller[6] = 20;
    reset_regs();
    if (getenv("EP5_TRACE")) trace = 1;
    cpus[0].regs[REG_D0] = 1;
    cpus[0].regs[REG_A0 + 2] = PACKET;
    cpus[0].regs[REG_A0 + 3] = CONTEXT;
    /* The synthetic caller executes call [..],48: the veneer's own 48-byte
     * save frame must not alias the stock envelope at param_sp+4. With a
     * 48-byte caller frame the veneer entry SP is STACK+0xf000-48 and the
     * deepest save lands 48 below it, clear of the envelope. */
    caller[6] = 48;
    cpus[0].regs[REG_SP] = STACK + 0xf000;
    param_sp = STACK + 0xf000 - 48;
    put(stack_ram + (param_sp - STACK) + 4, 0x123);
    put(stack_ram + (param_sp - STACK) + 8, 1);
    put(stack_ram + (param_sp - STACK) + 12, 1);
    put(stack_ram + (param_sp - STACK) + 16, PACKET);
    cpus[0].regs[REG_A0] = param_sp + 4;
    memcpy(param_registers, cpus[0].regs, sizeof param_registers);
    if (getenv("EP5_TRACE")) trace = 1;
    if (getenv("EP5_STEP")) {
        uint32_t last[32] = {0}, lsp[32] = {0}, lslot[32] = {0}; unsigned li = 0;
        for (unsigned long i = 0; i < 20000000 && !emu_stop; ++i) {
            last[li & 31] = cpus[0].regs[REG_PC];
            lsp[li & 31] = cpus[0].regs[REG_SP];
            lslot[li & 31] = mem_rd(cpus[0].regs[REG_SP], 4);
            ++li;
            cpu_run(1, 0);
        }
        fprintf(stderr, "last 32 (pc sp [sp]):\n");
        for (unsigned k = 0; k < 32; ++k) {
            unsigned idx = (li + k) & 31;
            fprintf(stderr, "  %x sp=%x [%x]\n", last[idx], lsp[idx], lslot[idx]);
        }
        fprintf(stderr, "final pc=%x sp=%x\n", cpus[0].regs[REG_PC], cpus[0].regs[REG_SP]);
    } else {
        /* The full-table CRC loop needs ~2.4M modeled instructions. */
        cpu_run(20000000, 0);
    }
    if (!reached_stop || !param_preserved || !send_envelope_valid || send_calls != 1 ||
        cpus[0].regs[REG_SP] != param_sp) {
        fprintf(stderr, "param phase failed stop=%d preserved=%d envelope=%d sends=%u sp=%x\n",
                reached_stop, param_preserved, send_envelope_valid, send_calls, cpus[0].regs[REG_SP]);
        for (unsigned i = 0; i < 8; ++i)
            if (i != REG_D0 && cpus[0].regs[i] != param_registers[i])
                fprintf(stderr, "  reg%u: %x -> %x\n", i, param_registers[i], cpus[0].regs[i]);
        fprintf(stderr, "  mdr: %x (want %x)\n", cpus[0].regs[REG_MDR], PARAM_CONTINUE);
        return 1;
    }
    unsigned neutralized = (mem_rd(PACKET + 6, 2) == 0);
    for (unsigned i = 80; i <= 90 && neutralized; ++i) neutralized &= packet[i] == 0;

    /* The stock ART consumer computes geometry after the send (NATIVE_CONTRACTS:
     * art_com_pass_init writes the six u16 at packet+80 once the size functions
     * run). The send-time neutralization clears them; model that later write so
     * the JPEG caller reads real dimensions instead of zero. The fixture is 4x20
     * YUYV (160 bytes); store and effective geometry match, offset zero. */
    put16(packet + 80, 4);
    put16(packet + 82, 20);
    put16(packet + 84, 4);
    put16(packet + 86, 20);
    put16(packet + 88, 0);
    put16(packet + 90, 0);

    /* ---- phase B: receive tail through the wait veneer (qualification) ---- */
    put(globals, word(config + 68));
    put(caller + 1, 0x7e3ed843u - CALLER);
    caller[6] = 44;
    reset_regs();
    put(stack_ram + 0xf000 - 44 + 4, 0x123);
    cpus[0].regs[REG_D0 + 2] = 0;
    cpus[0].regs[REG_A0 + 3] = word(config + 60);
    cpu_run(2000000, 0);
    uint32_t art_result = cpus[0].regs[REG_D0];
    if (!reached_stop || !wait_preserved || !wait_return_preserved ||
        cpus[0].regs[REG_SP] != STACK + 0xf000 || art_result != 0) {
        fprintf(stderr, "wait phase failed stop=%d preserved=%d/%d art=%x sp=%x\n",
                reached_stop, wait_preserved, wait_return_preserved, art_result, cpus[0].regs[REG_SP]);
        return 1;
    }

    /* ---- phase C: JPEG caller through the entry veneer (apply) ---- */
    put(globals, word(config + 40));
    put(caller + 1, 0x7e3ed85cu - CALLER);
    caller[6] = 56;
    reset_regs();
    cpu_run(50000000, 0);
    int preserved = cpus[0].regs[REG_SP] == STACK + 0xf000;
    const unsigned saved[] = {2, 3, REG_A0 + 2, REG_A0 + 3};
    for (unsigned i = 0; i < 4; ++i) preserved &= cpus[0].regs[saved[i]] == 0xabcd1000u + saved[i];
    if (!reached_stop || !preserved || !arguments_preserved || codec_calls != 1 ||
        bridge_count != 1 || cpus[0].regs[REG_D0] != 0x1234) {
        fprintf(stderr, "jpeg phase failed stop=%d preserved=%d args=%d codec=%u bridge=%u d0=%x\n",
                reached_stop, preserved, arguments_preserved, codec_calls, bridge_count, cpus[0].regs[REG_D0]);
        return 1;
    }
    uint32_t native_result = cpus[0].regs[REG_D0];

    /* ---- phase D: release fragment (look_release returns the pool block) ---- */
    reached_stop = emu_stop = 0;
    /* The stock release reads the pending buffer from ART_GLOBAL and frees it;
     * seed it with the real image base so FREE_BUFFER sees a valid pointer. */
    put(globals, word(config + 8));
    cpus[0].regs[REG_PC] = RELEASE_HOOK - 1;
    cpus[0].regs[REG_A0 + 2] = CONTEXT;
    uint32_t saved_regs[4];
    for (unsigned i = 0; i < 4; ++i) saved_regs[i] = cpus[0].regs[i < 2 ? i + 2 : i + 4];
    cpu_run(2000000, 0);
    if (!reached_stop || cpus[0].regs[REG_SP] != STACK + 0xf000 || mem_rd(ART_GLOBAL, 4))
        emu_abort(PC, "native release/frame failed");
    for (unsigned i = 0; i < 4; ++i)
        if (saved_regs[i] != cpus[0].regs[i < 2 ? i + 2 : i + 4])
            emu_abort(PC, "native release clobbered nonvolatile register");

    FILE *out = fopen(argv[5], "wb");
    if (!out || fwrite(pixels, 1, pixel_bytes, out) != pixel_bytes || fclose(out)) return 2;
    int balanced = pool_allocs == pool_frees && !pool_live;
    printf("{\"name\":\"%s\",\"direct\":%d,\"codec_calls\":%u,\"native_result\":%u,"
           "\"wait_calls\":%u,\"art_result\":%u,\"send_calls\":%u,\"release_calls\":%u,"
           "\"opens\":%d,\"reads\":%d,\"closes\":%d,\"pool_allocs\":%u,\"pool_frees\":%u,"
           "\"pool_balanced\":%s,\"pool_leaked\":%s,\"neutralized\":%u,\"state_writes\":%u,"
           "\"registers_and_stack_preserved\":true,\"native_arguments_preserved\":true,"
           "\"wait_return_preserved\":true,\"instructions\":%llu}\n",
           scenario, direct_backend, codec_calls, native_result, wait_calls, art_result,
           send_calls, release_calls, opened, read_calls, closed, pool_allocs, pool_frees,
           balanced ? "true" : "false", pool_live ? "true" : "false", neutralized, state_writes,
           (unsigned long long)cpus[0].icount);
    free(image);
    return 0;
}
