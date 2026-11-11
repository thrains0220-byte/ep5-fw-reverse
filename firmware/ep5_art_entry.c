#include "film.h"

extern const volatile uint32_t ep5_control[6];
extern const uint16_t ep5_embedded_lut[EP5_LUT_VALUES];

static uint16_t read16(const uint8_t *p)
{
    return (uint16_t)((unsigned)p[0] | (unsigned)p[1] << 8);
}

/* Candidate ABI adapter. Control stays disabled until the actual producer,
 * encoding, mapping ownership, cache and scheduling contracts are established. */
void ep5_art_before_jpeg(const uint8_t *request)
{
    struct ep5_image image;
    uint32_t start, size, last, address;
    uintptr_t req = (uintptr_t)request;
    if (ep5_control[0] != 0x43355045u || ep5_control[1] != 1 || !request)
        return;
    start = ep5_control[2];
    size = ep5_control[3];
    if (!start || !size || size - 1u > UINT32_MAX - start || req > UINT32_MAX - 39u)
        return;
    last = start + size - 1u;
    if ((start < 0x7e130000u && last >= 0x7e128010u) ||
        (start <= req + 39u && req <= last))
        return;
    address = (uint32_t)read16(request) | (uint32_t)read16(request + 2) << 16;
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
