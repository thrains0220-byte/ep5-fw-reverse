ENTRY(_ep5_probe)
SECTIONS
{
    .text 0x20000000 : { KEEP(*(.text.probe)) *(.text .text.*) }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
