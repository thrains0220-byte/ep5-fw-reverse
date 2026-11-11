ENTRY(_ep5_art_entry)
_ep5_native_codec = 0x7e3f4884;
_ep5_native_continue = 0x7e3ed8d6;
SECTIONS
{
    .text 0x7e128010 : { KEEP(*(.text.entry)) *(.text .text.*) }
    .rodata : { *(.rodata .rodata.*) }
    .control : ALIGN(4) { KEEP(*(.ep5.control)) }
    .lut : ALIGN(2) {
        KEEP(*(.ep5.lut))
        /* Explicit lookahead space for the instruction model. */
        LONG(0xcbcbcbcb) LONG(0xcbcbcbcb)
    }
    .data : { *(.data .data.* .sdata .sdata.*) }
    .bss : { *(.bss .bss.* .sbss .sbss.* COMMON) }
    ASSERT(. <= 0x7e130000, "module exceeds the E-P5 cave candidate")
    ASSERT(SIZEOF(.control) == 24, "unexpected control layout")
    ASSERT(SIZEOF(.lut) == 29486, "expected one RGB16 LUT plus lookahead")
    ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "module needs unqualified writable state")
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
