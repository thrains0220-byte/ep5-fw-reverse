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

/* One capture-task owner. Keep this object for the whole capture session.
 * The producer must carry the token issued at shutter time through its own
 * completion notification. Never substitute the most recently issued token. */
struct ep5_capture_sequence {
    uint32_t last, width, height;
    unsigned phase;
    struct ep5_lut_preload *owner;
    struct ep5_look_selection look;
    struct ep5_photo_style style;
    struct ep5_wheel_edit wheel;
};
enum ep5_capture_result {
    EP5_CAPTURE_IGNORED = -4, /* unrelated, cancelled or repeated event */
    EP5_CAPTURE_BYPASS = 2    /* no lease acquired; original owner still has the frame */
};
struct ep5_capture_backend {
    void *context;
    /* Success grants exclusive, CPU-readable ownership of this shot's
     * completed still frame. Failure must leave the native pipeline intact. */
    int (*claim)(void *, uint32_t token, struct ep5_image *image, unsigned *encoding);
    /* 1 transfers ownership to JPEG. If styled, make all writes visible
     * before transfer. On any other return, nothing was submitted and the
     * lease is still owned here. */
    int (*submit)(void *, uint32_t token, int photo_result);
    void (*discard)(void *, uint32_t token);
};
/* Zero-initialize once and keep at a stable address. Copy the settings and
 * pin the published table at shutter time. Keep loader and both backing
 * arrays alive through media changes until completion/cancel. Every accepted
 * token needs a matching completion or cancellation, including on shutdown.
 * Reset only after the producer and its completion queue have fully drained. */
uint32_t ep5_capture_begin(struct ep5_capture_sequence *sequence, struct ep5_lut_preload *loader,
                           uint32_t width, uint32_t height,
                           const struct ep5_shot_recipe *recipe, const struct ep5_camera_choice *choice);
int ep5_capture_cancel_pending(struct ep5_capture_sequence *sequence, uint32_t token);
/* Serialize with begin/cancel. In-flight cancellation uses progress as in
 * ep5_shot_develop. Only this call may submit or discard a claimed frame.
 * STOCK/STYLED mean already submitted. IGNORED must not trigger encoding. */
int ep5_capture_ready(struct ep5_capture_sequence *sequence, uint32_t token,
                      const struct ep5_capture_backend *backend,
                      const struct ep5_photo_workspace *work,
                      int (*progress)(void *, uint32_t, uint32_t), void *context);
#endif
