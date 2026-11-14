#ifndef EP5_LUT_MENU_INDEX_H
#define EP5_LUT_MENU_INDEX_H

#include "look_store.h"
#include "lut_menu.h"

/* Read and validate the bounded SD index from a file-task-owned IO context,
 * then publish a complete three-slot snapshot to the menu. The caller must
 * serialize the IO object and menu publication with the file worker. */
int ep5_lut_menu_load_index(const struct ep5_look_io *io,
                            struct ep5_lut_menu *menu, uint16_t generation);

#endif
