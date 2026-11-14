#include "film.h"
#include "look_store.h"
#ifdef EP5_DIAG
#include "diag.h"
#endif

extern const volatile uint32_t ep5_control[7];
extern volatile uint32_t ep5_ready[2];
extern volatile uint32_t ep5_look_state[4];

extern void *ep5_file_open(const char *path, const char *mode);
extern int32_t ep5_file_read(void *buffer, uint32_t size, uint32_t count, void *file);
extern void ep5_file_close(void *file);
extern int ep5_pool_alloc(uint32_t bytes, void **out);
extern void ep5_pool_free(void *pointer);

static uint16_t read16(const uint8_t *p)
{
    return (uint16_t)((unsigned)p[0] | (unsigned)p[1] << 8);
}

static uint32_t read32(const uint8_t *p)
{
    return (uint32_t)read16(p) | (uint32_t)read16(p + 2) << 16;
}

#ifndef EP5_DIAG
static const char ep5_mode_rb[] = "rb";

static void *look_open(void *context, const char *path)
{
    (void)context;
    return ep5_file_open(path, ep5_mode_rb);
}

static int32_t look_read(void *context, void *file, uint8_t *destination, uint32_t count)
{
    (void)context;
    return ep5_file_read(destination, 1, count, file);
}

static int look_close(void *context, void *file)
{
    (void)context;
    ep5_file_close(file);
    return 0;
}
#endif

static void look_release(void)
{
    if (ep5_look_state[3]) {
        ep5_pool_free((void *)(uintptr_t)ep5_look_state[3]);
        ep5_look_state[3] = 0;
    }
    ep5_look_state[0] = 0;
    ep5_look_state[1] = 0;
    ep5_look_state[2] = 0;
}

/* Mode 3: load the selected SD look before the stock send. Any failure keeps
 * the original packet and renders stock; the module never blocks a shot. */
static void look_prepare(uint8_t *packet, const uint8_t *context)
{
#ifdef EP5_DIAG
    /* Diagnostic build: never load a look, never neutralize the packet.
     * Excluded at compile time, not merely unreachable at run time. */
    (void)packet; (void)context;
    return;
#else
    const uint8_t *settings;
    const struct ep5_look_io io = {NULL, look_open, look_read, look_close};
    struct ep5_look_cache cache;
    struct ep5_look_selection selection;
    void *block = NULL;
    uint8_t *bytes;
    look_release();
    if (!context)
        return;
    settings = (const uint8_t *)(uintptr_t)read32(context + 84);
    if (!settings || read16(packet) != 1 || read16(packet + 2) != 3 ||
        packet[96] != 1 || packet[157] != 0 || read16(settings + 17442) != 0)
        return;
    /* One contiguous block guarantees the two tables cannot overlap:
     * exactly two 17^3 RGB16 tables, 58,956 bytes. */
    if (ep5_pool_alloc(2u * EP5_LUT_VALUES * 2u, &block) || !block)
        return;
    ep5_look_state[3] = (uintptr_t)block;
    bytes = (uint8_t *)block;
    if (ep5_look_cache_init(&cache, bytes, 2u * EP5_LUT_VALUES,
                            bytes + 2u * EP5_LUT_VALUES,
                            2u * EP5_LUT_VALUES) != EP5_LOOK_STOCK)
        return;
    if (ep5_look_load(&io, &cache, settings[17471], settings[18147], &selection) != EP5_LOOK_APPLY)
        return;
    /* Neutral ART list: keep RAW->YC, drop the extra filter and its colours. */
    packet[6] = packet[7] = 0;
    for (unsigned offset = 80; offset <= 90; ++offset)
        packet[offset] = 0;
    ep5_look_state[0] = (uintptr_t)cache.active;
    ep5_look_state[1] = (uintptr_t)cache.staging;
    ep5_look_state[2] = selection.amount_q8;
#endif
}

/* Stock clears packet geometry before send; mode 3 resolves to full size later. */
void ep5_param_before_send(uint8_t *packet, const uint8_t *context)
{
    const uint8_t *settings;
    if (ep5_control[0] != 0x43355045u ||
        packet != (uint8_t *)(uintptr_t)0x605f4510u || !context)
        return;
#ifdef EP5_DIAG
    if (ep5_control[1] == 4) {
        ep5_diag_init();
        return;
    }
#endif
    if (ep5_control[1] == 3) {
        look_prepare(packet, context);
        return;
    }
    if (ep5_control[1] != 2)
        return;
    settings = (const uint8_t *)(uintptr_t)read32(context + 84);
    if (!settings || settings[17471] != 105 || settings[18147] != 1 ||
        read16(packet) != 1 || read16(packet + 2) != 3 ||
        read16(packet + 6) != 73 || packet[96] != 1 ||
        read16(packet + 80) != 0 || read16(packet + 82) != 0 ||
        read16(packet + 84) != 0 || read16(packet + 86) != 0 ||
        read16(packet + 88) != 0 || read16(packet + 90) != 0 ||
        read16(settings + 17442) != 0 || packet[157] != 0)
        return;
    packet[157] = 1;
}

void ep5_art_before_release(void)
{
    if (ep5_control[0] == 0x43355045u && ep5_control[1] == 1)
        ep5_ready[0] = ep5_ready[1] = 0;
    if (ep5_control[0] == 0x43355045u && ep5_control[1] == 3)
        look_release();
#ifdef EP5_DIAG
    /* Diagnostic mode: the release hook attempts to flush observations.
     * Its file-service task context and timing are not hardware verified. */
    if (ep5_control[0] == 0x43355045u && ep5_control[1] == 4)
        (void)ep5_diag_flush();
#endif
}

void ep5_art_after_wait(const void *context, int32_t status, const uint8_t *reply)
{
    uint32_t buffer;
    if (ep5_control[0] != 0x43355045u ||
        (ep5_control[1] != 1 && ep5_control[1] != 3 && ep5_control[1] != 4))
        return;
    ep5_ready[0] = ep5_ready[1] = 0;
    if (!context || status != 0 || !reply || read16(reply) != 0 ||
        read32(reply + 4) != 1 || read32(reply + 8) != 0x605f4510u)
        return;
    /* Mode 3 only arms the JPEG apply once the SD look actually loaded:
     * an active table and a nonzero amount must survive from look_prepare.
     * This binds the qualification to this shot's loaded look, so a failed
     * or stock fallback never changes pixels. */
    if (ep5_control[1] == 3 && (!ep5_look_state[0] || !ep5_look_state[2]))
        return;
    buffer = *(const volatile uint32_t *)(uintptr_t)0x605f455cu;
    if (buffer) {
        ep5_ready[1] = buffer;
        ep5_ready[0] = (uintptr_t)context;
    }
}

#ifndef EP5_DIAG
static int range_ok(uint32_t start, uint32_t size, uintptr_t request)
{
    uint32_t last;
    if (!start || !size || size - 1u > UINT32_MAX - start)
        return 0;
    last = start + size - 1u;
    if (request > UINT32_MAX - 39u)
        return 0;
    if (request >> 29 == 3 || request >> 29 == 5) {
        uint32_t alternate = (uint32_t)request ^ 0xc0000000u;
        if ((request + 39u) >> 29 != request >> 29 ||
            (start <= alternate + 39u && alternate <= last))
            return 0;
    }
    if ((start < 0x7e130000u && last >= 0x7e128010u) ||
        (start < 0xbe130000u && last >= 0xbe128010u) ||
        (start <= request + 39u && request <= last))
        return 0;
    return 1;
}
#endif

/* Candidate ABI adapter. Control stays disabled until the actual producer,
 * encoding, mapping ownership, cache and scheduling contracts are established. */
void ep5_art_before_jpeg(const uint8_t *request, const void *context)
{
#ifndef EP5_DIAG
    struct ep5_image image;
    uint32_t start, size, address;
    const uint16_t *table;
    unsigned amount;
#else
    uint32_t address;
#endif
    uintptr_t req = (uintptr_t)request;
    if (ep5_control[0] != 0x43355045u || !request || req > UINT32_MAX - 39u ||
        (ep5_control[1] != 1 && ep5_control[1] != 3 && ep5_control[1] != 4))
        return;
    address = read32(request);
#ifdef EP5_DIAG
    /* Diagnostic mode: observe the real buffer contract, write nothing.
     * Qualification still binds to this shot's completion so a stale or
     * repeated JPEG request cannot log a foreign buffer. */
    if (ep5_control[1] == 4) {
        if (ep5_ready[0] == (uintptr_t)context && ep5_ready[1] == address &&
            context && address) {
            ep5_ready[0] = ep5_ready[1] = 0;
            (void)ep5_diag_observe(request, context, address);
        }
        return;
    }
#endif
    if (ep5_ready[0] != (uintptr_t)context || ep5_ready[1] != address || !context || !address)
        return;
    /* Consume before any pixel write: repeated JPEG requests cannot reapply it. */
    ep5_ready[0] = ep5_ready[1] = 0;
#ifndef EP5_DIAG
    if (ep5_control[1] == 3) {
        if (!ep5_look_state[2] || !ep5_look_state[0])
            return;
        table = (const uint16_t *)(uintptr_t)ep5_look_state[0];
        amount = ep5_look_state[2];
    } else {
        table = (const uint16_t *)(uintptr_t)ep5_control[6];
        amount = ep5_control[5];
        if (!table)
            return;
    }
    start = ep5_control[2];
    size = ep5_control[3];
    if (!range_ok(start, size, req))
        return;
    if (address < start || address - start >= size ||
        read16(request + 4) != read16(request + 8) ||
        read16(request + 6) != read16(request + 10) || (request[36] & 2u))
        return;
    image.data = (uint8_t *)(uintptr_t)address;
    image.capacity = size - (address - start);
    image.width = read16(request + 4);
    image.height = read16(request + 6);
    image.stride = (size_t)image.width * 2u;
    /* No callback: invalid inputs are rejected before mutation and cancellation
     * cannot leave a partially changed buffer on this synchronous test path. */
    (void)ep5_film_apply(&image, table, EP5_LUT_VALUES,
                         ep5_control[4], amount, NULL, NULL);
#else
    (void)req;
#endif /* !EP5_DIAG */
}
