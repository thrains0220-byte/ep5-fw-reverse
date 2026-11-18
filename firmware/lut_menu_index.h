#ifndef EP5_LUT_MENU_INDEX_H
#define EP5_LUT_MENU_INDEX_H

#include "lut_job.h"

/* Publish a finished index under the menu lock. An incomplete or stale job
 * leaves the menu alone. The worker reads the card outside this lock. */
int ep5_lut_menu_finish_index(const struct ep5_lut_job *job, struct ep5_lut_menu *menu);

/* Read and validate the bounded SD index from a file-task-owned IO context,
 * then publish a complete fourteen-slot snapshot to the menu. The caller must
 * serialize the IO object and menu publication with the file worker. */
int ep5_lut_menu_load_index(const struct ep5_look_io *io,
                            struct ep5_lut_menu *menu, uint16_t generation);

#endif
