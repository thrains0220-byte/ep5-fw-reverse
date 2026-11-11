/* Original E-P5 ART call-site veneer. The linker fixes the vendor frame targets. */
    .section .text.entry,"ax"
    .global _ep5_art_entry
_ep5_art_entry:
    /* GCC owns the return slot and eight-byte argument flushback area. */
    add -48,sp
    mov d0,(12,sp)
    mov d1,(16,sp)
    mov a0,(20,sp)
    mov a1,(24,sp)
    mov d2,(28,sp)
    mov d3,(32,sp)
    mov a2,(36,sp)
    mov a3,(40,sp)
    mov mdr,d0
    mov d0,(44,sp)
    mov a1,d0
    call _ep5_art_before_jpeg,[],0
    mov (44,sp),d0
    mov d0,mdr
    mov (12,sp),d0
    mov (16,sp),d1
    mov (20,sp),a0
    mov (24,sp),a1
    mov (28,sp),d2
    mov (32,sp),d3
    mov (36,sp),a2
    mov (40,sp),a3
    add 48,sp
    .global _ep5_codec_call
_ep5_codec_call:
    call _ep5_native_codec,[d2,d3,a2,a3],16
    jmp _ep5_native_continue

    .section .ep5.control,"a"
    .balign 4
    .global _ep5_control
_ep5_control:
    .long 0x43355045,0,0,0,0,0
