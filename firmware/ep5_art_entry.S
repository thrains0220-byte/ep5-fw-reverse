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
    .long 0x43355045,0,0,0,0,0,0

    .section .ep5.state,"aw"
    .balign 4
    .global _ep5_ready_storage
_ep5_ready_storage:
    .long 0,0
    .global _ep5_look_state_storage
_ep5_look_state_storage:
    .long 0,0,0,0

    .section .text
    .global _ep5_file_open
_ep5_file_open:
    /* GCC MN103 passes the first two args in D0/D1 and returns pointers in
     * A0. The stock wrapper wants path=A0, mode=A1 and frames ret [a2,a3],28.
     * GCC calls this veneer with call [],0, so the caller's return address
     * sits at SP; reserve our own frame first or the nested call overwrites it. */
    /* D2/D3/A2/A3 are GCC callee-saved: the stock frame only restores what
     * the stock call captured, so stash the incoming values above it.
     * look_load keeps io in A3 across this call. */
    add -44,sp
    mov d2,(28,sp)
    mov d3,(32,sp)
    mov a2,(36,sp)
    mov a3,(40,sp)
    mov d0,a0
    mov d1,a1
    mov a0,a2
    mov a1,a3
    call _ep5_native_file_open,[a2,a3],28
    mov (28,sp),d2
    mov (32,sp),d3
    mov (36,sp),a2
    mov (40,sp),a3
    add 44,sp
    ret [],0
    .global _ep5_file_read
_ep5_file_read:
    /* GCC args: D0=dst, D1=size; args 3/4 are on the stack at SP+12/SP+16
     * (proven by look_read disassembly and a runtime register dump: this
     * toolchain does NOT pass arg3/arg4 in A0/A1). Stock wants dst=A0,
     * size=D0, count=D1, file=A1; frame ret [d2,d3,a2,a3],40. Load the stack
     * args into A0/A1 before touching SP, then build the stock args and save
     * the incoming callee-saved registers above the stock frame. */
    mov (12,sp),a0
    mov (16,sp),a1
    add -60,sp
    mov d2,(40,sp)
    mov d3,(44,sp)
    mov a2,(48,sp)
    mov a3,(52,sp)
    /* D0=dst, D1=size, A0=count, A1=file -> A0=dst, D0=size, D1=count, A1=file.
     * Park dst in a fifth frame slot (56,sp): only D0/D1/A0 are scratch here,
     * so d2/d3/a2/a3 still hold the incoming callee-saved values when the call
     * mask saves them and the stock ret restores them. */
    mov d0,(56,sp)
    mov d1,d0
    mov a0,d1
    mov (56,sp),a0
    call _ep5_native_file_read,[d2,d3,a2,a3],40
    mov (40,sp),d2
    mov (44,sp),d3
    mov (48,sp),a2
    mov (52,sp),a3
    add 60,sp
    ret [],0
    .global _ep5_file_close
_ep5_file_close:
    /* GCC arg D0=file; stock wants A0=file, frame ret [a2],16. */
    add -32,sp
    mov d2,(16,sp)
    mov d3,(20,sp)
    mov a2,(24,sp)
    mov a3,(28,sp)
    mov d0,a0
    mov a0,a2
    call _ep5_native_file_close,[a2],16
    mov (16,sp),d2
    mov (20,sp),d3
    mov (24,sp),a2
    mov (28,sp),a3
    add 32,sp
    ret [],0
    .global _ep5_file_write
_ep5_file_write:
    /* Mirrors _ep5_file_read (proven ABI). GCC args: D0=buf, D1=size;
     * arg3=count at SP+12, arg4=file at SP+16. Stock wants A0=buf, D0=size,
     * D1=count, A1=file; frame ret [d2,d3,a2,a3],40. */
    mov (12,sp),a0
    mov (16,sp),a1
    add -60,sp
    mov d2,(40,sp)
    mov d3,(44,sp)
    mov a2,(48,sp)
    mov a3,(52,sp)
    mov d0,(56,sp)
    mov d1,d0
    mov a0,d1
    mov (56,sp),a0
    call _ep5_native_file_write,[d2,d3,a2,a3],40
    mov (40,sp),d2
    mov (44,sp),d3
    mov (48,sp),a2
    mov (52,sp),a3
    add 60,sp
    ret [],0
    .global _ep5_pool_alloc
_ep5_pool_alloc:
    add -52,sp
    mov d2,(36,sp)
    mov d3,(40,sp)
    mov a2,(44,sp)
    mov a3,(48,sp)
    /* GCC args: D0=bytes, D1=out**. Stock inputs (proven pixel probe):
     * D0=bytes, D1=0, A0=out**, A1=tag; mode at callee SP+36, line at +40.
     * With call N=32 those are veneer SP+4/+8. The wrapper writes the block
     * pointer to *A0 itself and returns a 16-bit status in D0. Capture out**
     * into A0 FIRST: D1 is reused as the mode/line scratch below. */
    mov d1,a0
    mov _ep5_pool_tag,a1
    mov 3,d1
    mov d1,(4,sp)
    mov 0x4e4,d1
    mov d1,(8,sp)
    mov 0,d1
    call _ep5_native_pool_alloc,[d2,d3,a2,a3],32
    mov (36,sp),d2
    mov (40,sp),d3
    mov (44,sp),a2
    mov (48,sp),a3
    add 52,sp
    ret [],0
    .global _ep5_pool_free
_ep5_pool_free:
    /* GCC arg D0=ptr; stock wants D0=ptr, D1=mode(3), frame ret [d2,d3],12. */
    add -28,sp
    /* Park D0 at +4: the nested call stores its return address at (0,sp). */
    mov d0,(4,sp)
    mov d2,(12,sp)
    mov d3,(16,sp)
    mov a2,(20,sp)
    mov a3,(24,sp)
    mov 3,d1
    mov d0,d2
    mov d1,d3
    call _ep5_native_pool_free,[d2,d3],12
    mov (12,sp),d2
    mov (16,sp),d3
    mov (20,sp),a2
    mov (24,sp),a3
    mov (4,sp),d0
    add 28,sp
    ret [],0

    .section .rodata
_ep5_pool_tag:
    .asciz "EP5LUT"
