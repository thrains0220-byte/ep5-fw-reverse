    .section .text.probe,"ax"
    .global _ep5_probe
_ep5_probe:
    add -40,sp
    mov 0x11111111,d0
    mov d0,(0,sp)
    mov 0x22222222,d0
    mov d0,(4,sp)
    mov 0x12345678,d0
    mov d0,(8,sp)
    mov 0x9abcdef0,d0
    mov d0,(12,sp)
    mov 0x33333333,d0
    mov d0,(36,sp)
    mov 0x44444444,d0
    mov d0,(40,sp)
    mov 0x55555555,d2
    mov 0x66666666,d3
    call _target,[d2,d3],32
    /* Returning here proves the whole call/ret chain unwound correctly. */
    /* (40,sp) is the caller's return slot, overwritten by call; reload the
     * sentinel from a frame slot the callee never touches instead. */
    mov (8,sp),d0
    mov (4,sp),d1
    mov (36,sp),a0
    mov (12,sp),a1
    add 40,sp
    /* The model entry SP holds no return address; jump to the sentinel end. */
    jmp _probe_end
    .global _target
_target:
    /* Caller stored our return address at S; callee SP = S-32, so (32,sp)=S. */
    mov (32,sp),a2
    /* The callee owns its 4-byte frame: push, call, release, then ret. */
    add -4,sp
    call _inner,[],0
    add 4,sp
    mov 0x88888888,d0
    /* ret N must undo the caller's full frame: SP+=32 restores d2/d3 from
     * S-4/S-8 and reads the return address from S. */
    ret [d2,d3],32
    .global _inner
_inner:
    mov 0x99999999,d1
    ret [],0
    .global _probe_end
_probe_end:
    jmp _probe_end
