/* D diagnostic branch linker script. Same cave candidate and proven hook
 * targets as ep5_art_entry.ld, but permits a bounded .bss for observation
 * records (8 x 128 B). Still no .data; state alias rules unchanged. */
ENTRY(_ep5_art_entry)
_ep5_native_codec = 0x7e3f4884;
_ep5_native_continue = 0x7e3ed8d6;
_ep5_native_wait = 0x7e3f7fa7;
_ep5_wait_continue = 0x7e3ed857;
_ep5_native_release = 0x7e3edac1;
_ep5_release_continue = 0x7e3f247b;
_ep5_native_send = 0x7e3fca97;
_ep5_param_continue = 0x7e3ed83c;
_ep5_native_file_open = 0x7e291515;
_ep5_native_file_read = 0x7e2915ea;
_ep5_native_file_close = 0x7e291557;
_ep5_native_file_write = 0x7e29159b;
_ep5_native_pool_alloc = 0x7e40a3fc;
_ep5_native_pool_free = 0x7e40a4f0;
SECTIONS
{
    .text 0x7e128010 : { KEEP(*(.text.entry)) *(.text .text.*) }
    .rodata : { *(.rodata .rodata.*) }
    .control : ALIGN(4) { KEEP(*(.ep5.control)) }
    .state : ALIGN(4) { KEEP(*(.ep5.state)) }
    _ep5_ready = _ep5_ready_storage + 0x40000000;
    _ep5_look_state = _ep5_look_state_storage + 0x40000000;
    /* NOBITS .bss would be dropped by objcopy -O binary. The builder appends
     * 0xFF filler for this window after objcopy (see build_diag_payload), so
     * the flat boot image covers it and ep5_diag_init clears it at run time. */
    .bss (NOLOAD) : ALIGN(4) {
        PROVIDE(_ep5_diag_bss_start = .);
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(4);
        PROVIDE(_ep5_diag_bss_end = .);
    }
    .data : { *(.data .data.* .sdata .sdata.*) }
    ASSERT(. <= 0x7e130000, "module exceeds the E-P5 cave candidate")
    ASSERT(SIZEOF(.control) == 28, "unexpected control layout")
    ASSERT(SIZEOF(.state) == 24, "unexpected qualification state layout")
    ASSERT(SIZEOF(.data) == 0, "diagnostic module needs no initialized data")
    ASSERT(SIZEOF(.bss) <= 2048, "diagnostic observation buffer too large")
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
