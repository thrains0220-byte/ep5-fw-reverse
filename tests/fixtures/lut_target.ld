ENTRY(_ep5_probe)
_ep5_probe_done = 0x2000fff0;
SECTIONS
{
    .text 0x20000000 : {
        KEEP(*(.text.probe)) *(.text .text.*) *(.rodata .rodata.*)
        /* The CPU engine fetches eight bytes even for the final short instruction. */
        LONG(0xcbcbcbcb) LONG(0xcbcbcbcb)
    }
    .data : { *(.data .data.* .sdata .sdata.*) }
    .bss : { *(.bss .bss.* .sbss .sbss.* COMMON) }
    ASSERT(SIZEOF(.text) < 0xfff0, "test code overlaps stop address")
    ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "fixture needs unexpected initialization")
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
