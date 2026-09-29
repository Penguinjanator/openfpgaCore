SOURCE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(SOURCE_DIR)/../../../..)
BUILD_DIR ?= $(abspath $(SOURCE_DIR)/../obj_dir_cpu_i2f)
BENCH ?= $(abspath $(SOURCE_DIR)/../obj_dir_system_mister/Vtb_system)

.PHONY: all firmware run
all: $(BUILD_DIR)/i2f.bin

$(BUILD_DIR)/generated.stamp: $(SOURCE_DIR)/generate.py
	python3 $< $(BUILD_DIR)
	touch $@

$(BUILD_DIR)/i2f.bin: $(BUILD_DIR)/generated.stamp $(SOURCE_DIR)/main.c \
                         $(SOURCE_DIR)/start.S $(SOURCE_DIR)/link.ld $(SOURCE_DIR)/Makefile
	bash $(REPO_ROOT)/tools/firmware-container.sh -f $(SOURCE_DIR)/Makefile \
		firmware BUILD_DIR=$(BUILD_DIR)

# Invoked inside the official firmware container by the rule above.
firmware:
	riscv64-unknown-elf-gcc -march=rv32imafc_zicsr_zifencei -mabi=ilp32f -O2 \
		-ffreestanding -fno-builtin -nostdlib -nostartfiles -I$(BUILD_DIR) \
		-Wl,-T,$(SOURCE_DIR)/link.ld -Wl,--no-relax \
		$(SOURCE_DIR)/start.S $(SOURCE_DIR)/main.c -o $(BUILD_DIR)/i2f.elf
	riscv64-unknown-elf-objcopy -O binary $(BUILD_DIR)/i2f.elf $(BUILD_DIR)/i2f.bin

run: all
	cd $(BUILD_DIR) && $(BENCH) i2f.bin 80000000
