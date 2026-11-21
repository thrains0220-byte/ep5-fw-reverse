/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef EP5_FILM_FX_PRESET_H
#define EP5_FILM_FX_PRESET_H
#include "film_fx.h"
#include "look_store.h"
#include "lut_menu.h"

#define EP5_FILM_FX_PRESET_PATH "EP5LUT/FX.EP5"
#define EP5_FILM_FX_PRESET_MAX_BYTES (20u + EP5_LUT_MENU_SLOTS * 16u)

/* The worker provides an exact, complete file from the same mount and bank
 * as the LUT. Pass the confirmed choice after its LUT CRC was validated.
 * A missing file is (NULL, 0). The function returns 1 for a matching row,
 * 0 for no file/no match, or -1 for malformed input. In both latter cases,
 * it supplies disabled settings. seed is selected by the caller per shot. */
int ep5_film_fx_preset(const uint8_t *data, size_t bytes,
                       const struct ep5_lut_menu_capture *choice, uint32_t seed,
                       struct ep5_film_fx_settings *out);

/* Worker convenience wrapper. io must be bound to the same mount and bank
 * as choice. Read through EOF and close before publishing settings. Do not
 * call from a menu event, drawing callback or capture path. */
int ep5_film_fx_preset_load(const struct ep5_look_io *io,
                            const struct ep5_lut_menu_capture *choice, uint32_t seed,
                            struct ep5_film_fx_settings *out);
#endif
