# Host builds of the firmware: unit tests and the firmware in the loop
# simulator. The sources under src/ are the ones a target build compiles; only
# the HAL implementation differs.
#
#   make test    unit tests, with address and undefined behaviour sanitisers
#   make sim     build/daq_sim, the firmware in the loop runner
#   make arm     compile src/ for Cortex-M4F, if arm-none-eabi-gcc is present
#   make clean

CC ?= gcc
BUILD := build
SRC := src/adc_spi.c src/sampling_engine.c src/calibration.c src/host_link.c src/daq_app.c
MOCK := host/mock_ad7124.c
TESTS := test/test_main.c test/test_adc_spi.c test/test_sampler.c \
         test/test_calibration.c test/test_host_link.c test/test_daq_app.c
WARN := -std=c11 -Wall -Wextra -Werror -Wpedantic -Wshadow -Wconversion \
        -Wno-sign-conversion
INC := -Iinclude -Ihost -Itest
SAN := -fsanitize=address,undefined -fno-sanitize-recover=all

.PHONY: all test sim arm clean
all: test sim

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/unit_tests: $(SRC) $(MOCK) $(TESTS) test/fixtures/cal_vectors.h $(wildcard include/*.h host/*.h test/*.h) | $(BUILD)
	$(CC) $(WARN) $(INC) -O1 -g $(SAN) $(SRC) $(MOCK) $(TESTS) -o $@

test: $(BUILD)/unit_tests
	./$(BUILD)/unit_tests

$(BUILD)/daq_sim: $(SRC) $(MOCK) host/daq_sim.c $(wildcard include/*.h host/*.h) | $(BUILD)
	$(CC) $(WARN) $(INC) -O2 $(SRC) $(MOCK) host/daq_sim.c -o $@

sim: $(BUILD)/daq_sim

# Compile only: there is no board support package or linker script yet, so
# this proves the portable sources build cleanly for the target core and
# reports their size, nothing more.
ARM_CC := arm-none-eabi-gcc
ARM_FLAGS := -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16 -Os \
             -ffunction-sections -fdata-sections
arm: | $(BUILD)
	@command -v $(ARM_CC) >/dev/null || { echo "arm-none-eabi-gcc not installed"; exit 1; }
	mkdir -p $(BUILD)/arm
	for f in $(SRC); do \
		$(ARM_CC) $(WARN) -Iinclude $(ARM_FLAGS) -c $$f -o $(BUILD)/arm/$$(basename $$f .c).o || exit 1; \
	done
	arm-none-eabi-size -t $(BUILD)/arm/*.o

clean:
	rm -rf $(BUILD)
