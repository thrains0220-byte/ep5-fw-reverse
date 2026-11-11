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
    mov a0,d1
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

    .global _ep5_wait_entry
_ep5_wait_entry:
    add -12,sp
    mov a0,(4,sp)
    mov a3,(8,sp)
    /* Queue wrapper discards length: poison fields before receiving. */
    mov d0,(0,sp)
    mov -1,d0
    mov d0,(a0)
    mov d0,(4,a0)
    mov 0,d0
    mov d0,(8,a0)
    mov (0,sp),d0
    .global _ep5_wait_call
_ep5_wait_call:
    call _ep5_native_wait,[],20
    /* Third GCC argument at12; register saves must start after it. */
    add -52,sp
    mov d0,(16,sp)
    mov d1,(20,sp)
    mov a0,(24,sp)
    mov a1,(28,sp)
    mov d2,(32,sp)
    mov d3,(36,sp)
    mov a2,(40,sp)
    mov a3,(44,sp)
    mov mdr,d0
    mov d0,(48,sp)
    mov (56,sp),d0
    mov d0,(12,sp)
    mov (60,sp),d0
    mov (16,sp),d1
    call _ep5_art_after_wait,[],0
    mov (48,sp),d0
    mov d0,mdr
    mov (16,sp),d0
    mov (20,sp),d1
    mov (24,sp),a0
    mov (28,sp),a1
    mov (32,sp),d2
    mov (36,sp),d3
    mov (40,sp),a2
    mov (44,sp),a3
    add 52,sp
    add 12,sp
    jmp _ep5_wait_continue

    .global _ep5_release_entry
_ep5_release_entry:
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
    call _ep5_art_before_release,[],0
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
    call _ep5_native_release,[],4
    jmp _ep5_release_continue

    .global _ep5_param_entry
_ep5_param_entry:
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
    mov a2,d0
    mov a3,d1
    call _ep5_param_before_send,[],0
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
    .global _ep5_param_call
_ep5_param_call:
    call _ep5_native_send,[d2,a2],20
    add -4,sp
    mov d0,(0,sp)
    mov 0x7e3ed83c,d0
    mov d0,mdr
    mov (0,sp),d0
    add 4,sp
    jmp _ep5_param_continue

    .section .ep5.control,"a"
    .balign 4
    .global _ep5_control
_ep5_control:
    .long 0x43355045,0,0,0,0,0

    .section .ep5.state,"aw"
    .balign 4
    .global _ep5_ready_storage
_ep5_ready_storage:
    .long 0,0
