/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef EP5_FILM_SHOT_H
#define EP5_FILM_SHOT_H
#include "film_photo.h"
#include "lut_camera_menu.h"

struct ep5_shot_recipe {
    struct ep5_lut_menu_capture look;
    struct ep5_film_fx_settings fx;
    uint32_t mount, revision, medium;
    unsigned bank;
};

/* File worker. choice is a copy obtained from the UI owner. io is bound to
 * that mount/bank. The preloader must have finished loading this same table
 * before a recipe is published. medium is its unique mount/bank token.
 * NULL io selects colour only. A missing or damaged FX file leaves texture
 * off. Returns the FX preset status. */
int ep5_shot_prepare(struct ep5_shot_recipe *recipe, const struct ep5_camera_choice *choice,
                     const struct ep5_look_io *io, uint32_t medium, uint32_t grain_seed);

/* Capture task. Supply a fresh, serialized UI snapshot at shutter time.
 * recipe and current may belong to different revisions: this is an ordinary
 * stock fallback and must not use the old table or wheel. No file access. */
int ep5_shot_develop(struct ep5_lut_preload *loader, uint32_t shot,
                     const struct ep5_shot_recipe *recipe, const struct ep5_camera_choice *current,
                     const struct ep5_image *image, unsigned encoding,
                     const struct ep5_photo_workspace *work,
                     int (*progress)(void *, uint32_t, uint32_t), void *context);
#endif
