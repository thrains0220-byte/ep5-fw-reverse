#include "film.h"

extern const volatile uint32_t ep5_control[6];
extern const uint16_t ep5_embedded_lut[EP5_LUT_VALUES];
extern volatile uint32_t ep5_ready[2];

static uint16_t read16(const uint8_t *p)
{
    return (uint16_t)((unsigned)p[0] | (unsigned)p[1] << 8);
}

static uint32_t read32(const uint8_t *p)
{
    return (uint32_t)read16(p) | (uint32_t)read16(p + 2) << 16;
}

/* Experimental route A: one neutral contrast step in one full-size ART request. */
void ep5_param_before_send(uint8_t *packet, const uint8_t *context)
{
    const uint8_t *settings;
    if (ep5_control[0] != 0x43355045u || ep5_control[1] != 2 ||
        packet != (uint8_t *)(uintptr_t)0x605f4510u || !context)
        return;
    settings = *(const uint8_t *const *)(context + 84);
    if (!settings || settings[17471] != 105 || settings[18147] != 1 ||
        read16(packet + 6) != 73 || packet[96] != 1 ||
        read16(packet + 80) != 4608 || read16(packet + 82) != 3456 ||
        read16(packet + 84) != 4608 || read16(packet + 86) != 3456 ||
        read16(settings + 17442) != 0 || packet[157] != 0)
        return;
    packet[157] = 1;
}

void ep5_art_before_release(void)
{
    if (ep5_control[0] == 0x43355045u && ep5_control[1] == 1)
        ep5_ready[0] = ep5_ready[1] = 0;
}

void ep5_art_after_wait(const void *context, int32_t status, const uint8_t *reply)
{
    uint32_t buffer;
    if (ep5_control[0] != 0x43355045u || ep5_control[1] != 1)
        return;
    ep5_ready[0] = ep5_ready[1] = 0;
    if (!context || status != 0 || !reply || read16(reply) != 0 ||
        read32(reply + 4) != 1 || read32(reply + 8) != 0x605f4510u)
        return;
    buffer = *(const volatile uint32_t *)(uintptr_t)0x605f455cu;
    if (buffer) {
        ep5_ready[1] = buffer;
        ep5_ready[0] = (uintptr_t)context;
    }
}

/* Candidate ABI adapter. Control stays disabled until the actual producer,
 * encoding, mapping ownership, cache and scheduling contracts are established. */
void ep5_art_before_jpeg(const uint8_t *request, const void *context)
{
    struct ep5_image image;
    uint32_t start, size, last, address;
    uintptr_t req = (uintptr_t)request;
    if (ep5_control[0] != 0x43355045u || ep5_control[1] != 1 || !request || req > UINT32_MAX - 39u)
        return;
    address = read32(request);
    if (ep5_ready[0] != (uintptr_t)context || ep5_ready[1] != address || !context || !address)
        return;
    /* Consume before any pixel write: repeated JPEG requests cannot reapply it. */
    ep5_ready[0] = ep5_ready[1] = 0;
    start = ep5_control[2];
    size = ep5_control[3];
    if (!start || !size || size - 1u > UINT32_MAX - start)
        return;
    last = start + size - 1u;
    if (req >> 29 == 3 || req >> 29 == 5) {
        uint32_t alternate = (uint32_t)req ^ 0xc0000000u;
        if ((req + 39u) >> 29 != req >> 29 ||
            (start <= alternate + 39u && alternate <= last))
            return;
    }
    if ((start < 0x7e130000u && last >= 0x7e128010u) ||
        (start < 0xbe130000u && last >= 0xbe128010u) ||
        (start <= req + 39u && req <= last))
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
    (void)ep5_film_apply(&image, ep5_embedded_lut, EP5_LUT_VALUES,
                         ep5_control[4], ep5_control[5], NULL, NULL);
}
