/*
 * Hardware abstraction for the converter's SPI bus and control lines.
 *
 * The driver never touches a peripheral register. On the STM32 target these
 * callbacks wrap the SPI peripheral (mode 3), a GPIO for chip select, the
 * DOUT/RDY line and a microsecond delay; on the host they are served by the
 * mocked device in firmware/host/mock_ad7124.c. Keeping the boundary this
 * narrow is what lets every line of the driver run in a host unit test.
 */
#ifndef HAL_SPI_H
#define HAL_SPI_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    void *ctx;
    /* One complete transaction: chip select asserted for all n bytes, rx may
     * be NULL. Returns 0 on success, negative on a bus error. */
    int (*xfer)(void *ctx, const uint8_t *tx, uint8_t *rx, size_t n);
    /* True while DOUT/RDY is low, that is when a conversion is ready. */
    bool (*data_ready)(void *ctx);
    void (*delay_us)(void *ctx, uint32_t us);
} hal_spi_t;

/* Front end input selection, driven by GPIO on the board: the signal
 * connector, a relay that shorts the input pair for a zero reading, or the
 * calibration reference connector. */
typedef enum {
    INPUT_SIGNAL = 0,
    INPUT_SHORT = 1,
    INPUT_CAL_REF = 2
} daq_input_t;

typedef struct {
    void *ctx;
    void (*select_input)(void *ctx, daq_input_t input);
    void (*select_gain)(void *ctx, unsigned gain_index);
} hal_frontend_t;

#endif
