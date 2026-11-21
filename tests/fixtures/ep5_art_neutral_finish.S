/* SPDX-License-Identifier: GPL-3.0-or-later
 * MN103 model payload. Never linked into a camera update.
 * Native worker passes the record body in A0 and expects the result in D0.
 */
    .text
    .global ep5_art_neutral_finish
ep5_art_neutral_finish:
    mov (12,a0),d0              /* stage mask after RAW-to-YC pass 7 */
    cmp 0xffff,d0
    bne .Lwaiting
    mov (16,a0),d0              /* ISP result */
    cmp 0,d0
    bne .Lfailed
    mov (8,a0),a1               /* this task's ART packet */
    cmp 0x605f4510,a1
    bne .Lfailed
    mov (36,a0),d0              /* image address published by pass 7 */
    cmp 0,d0
    beq .Lfailed
    mov (76,a1),d1
    cmp d1,d0
    bne .Lfailed
    mov 2,d0
    retf [],0
.Lwaiting:
    mov 1,d0
    retf [],0
.Lfailed:
    mov 0xfffe,d0
    retf [],0
