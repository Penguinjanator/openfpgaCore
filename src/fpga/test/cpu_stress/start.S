.section .text.start,"ax"
.global _start
_start:
  .option push
  .option norelax
  la gp, __global_pointer$
  .option pop
  li sp, 0x103ffff0
  li t0, 0x6000
  csrs mstatus, t0
  la t0, trap
  csrw mtvec, t0
  la t0, __bss_start
  la t1, __bss_end
1:
  bgeu t0, t1, 2f
  sw zero, 0(t0)
  addi t0, t0, 4
  j 1b
2:
  call main
3:
  j 3b
.balign 4
trap:
  addi sp, sp, -16
  sw t0, 0(sp)
  sw t1, 4(sp)
  csrr t0, mcause
  li t1, 11
  bne t0, t1, 3b
  la t0, traps
  lw t1, 0(t0)
  addi t1, t1, 1
  sw t1, 0(t0)
  csrr t0, mepc
  addi t0, t0, 4
  csrw mepc, t0
  lw t0, 0(sp)
  lw t1, 4(sp)
  addi sp, sp, 16
  mret
