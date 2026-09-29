ENTRY(_start)
SECTIONS {
  . = 0x10320000;
  .text : { *(.text.start) *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) *(.sdata*) }
  . = ALIGN(16);
  __global_pointer$ = . + 0x800;
  __bss_start = .;
  .bss : { *(.bss*) *(.sbss*) *(COMMON) }
  . = ALIGN(16);
  __bss_end = .;
}
