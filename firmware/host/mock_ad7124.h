/*
 * A mocked AD7124-8 class converter on a mocked SPI bus.
 *
 * Implements the register file, the communications register protocol, the
 * 64 ones serial reset, the data register with the optional appended status
 * byte and the DOUT/RDY line, independently of the driver: register sizes and
 * reset values are written out here again rather than borrowed from
 * adc_spi.c, so a driver bug in either cannot hide in both.
 *
 * Conversion results come from a callback, which in the firmware in the loop
 * run serves codes produced by the behavioural converter model. Faults can be
 * injected: a wrong ID, a stuck RDY line, a device error flag and a bus
 * failure. Every transaction is logged so tests can assert exact bytes.
 */
#ifndef MOCK_AD7124_H
#define MOCK_AD7124_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "hal_spi.h"

#define MOCK_LOG_DEPTH 64
#define MOCK_MAX_XFER 16

typedef struct {
    uint8_t tx[MOCK_MAX_XFER];
    size_t n;
} mock_xfer_t;

typedef struct {
    uint32_t regs[0x39];
    bool ready;
    bool auto_ready;          /* RDY asserts whenever the source has data */
    /* Conversion source: returns false when it has nothing more to give. */
    bool (*next_code)(void *ctx, int32_t *code);
    void *source_ctx;

    /* Fault injection. */
    uint8_t id_value;
    bool stuck_not_ready;
    bool error_flag;
    bool ignore_writes;       /* acknowledge writes, keep old values */
    int fail_bus_after;       /* -1 never; else fail once this many xfers done */

    /* Observability. */
    mock_xfer_t log[MOCK_LOG_DEPTH];
    unsigned log_count;       /* total, the log keeps the last MOCK_LOG_DEPTH */
    unsigned resets;
    unsigned protocol_errors;
    unsigned conversions;
    uint64_t elapsed_us;
} mock_ad7124_t;

void mock_init(mock_ad7124_t *m);
void mock_power_on(mock_ad7124_t *m);
hal_spi_t mock_hal(mock_ad7124_t *m);
const mock_xfer_t *mock_last(const mock_ad7124_t *m, unsigned back);
unsigned mock_reg_size(uint8_t reg);

#endif
