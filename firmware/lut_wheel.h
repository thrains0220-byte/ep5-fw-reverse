#ifndef EP5_LUT_WHEEL_H
#define EP5_LUT_WHEEL_H
#include <stddef.h>
#include <stdint.h>
#include "lut.h"

#define EP5_WHEEL_SECTORS 12u
#define EP5_WHEEL_NODES (EP5_LUT_VALUES / 3u)
#define EP5_WHEEL_FILE_BYTES 56u
enum ep5_wheel_axis { EP5_WHEEL_HUE, EP5_WHEEL_SAT, EP5_WHEEL_LIGHT };
struct ep5_wheel_values { int8_t axis[3][EP5_WHEEL_SECTORS]; };
struct ep5_wheel_edit {
    uint16_t picture_mode, number;
    uint8_t variant;
    uint32_t look_crc;
    struct ep5_wheel_values values;
};
int ep5_wheel_valid(const struct ep5_wheel_values *values);
int ep5_wheel_same_look(const struct ep5_wheel_edit *a, const struct ep5_wheel_edit *b);
void ep5_wheel_copy(struct ep5_wheel_edit *out, const struct ep5_wheel_edit *edit);
int ep5_wheel_encode(const struct ep5_wheel_edit *edit, uint8_t *out, size_t size);
int ep5_wheel_decode(const uint8_t *data, size_t size, struct ep5_wheel_edit *out);
/* Red-fastest RGB16 words, with edits applied after base. NULL base produces an
 * edited identity table. Source and destination are complete, disjoint buffers
 * (or exactly identical). In-place chunks must each be visited exactly once. */
int ep5_wheel_bake(const struct ep5_wheel_values *values,
                   const uint16_t *base, size_t base_words,
                   uint16_t *dest, size_t dest_words, unsigned first, unsigned count);
#endif
