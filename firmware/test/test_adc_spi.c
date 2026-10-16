/*
 * Driver tests against the mocked converter: exact bytes on the bus, the
 * register map, configuration with read back and the failure paths.
 */
#include <string.h>

#include "adc_spi.h"
#include "mock_ad7124.h"
#include "unit.h"

static mock_ad7124_t dev;
static adc_t adc;

static void setup(void)
{
    mock_init(&dev);
    hal_spi_t h = mock_hal(&dev);
    adc_init(&adc, &h);
}

static void test_register_sizes_match_mock(void)
{
    /* The driver and the mock each carry their own table. */
    for (unsigned r = 0; r < 0x40; r++)
        CHECK_EQ(adc_reg_size((uint8_t)r), mock_reg_size((uint8_t)r));
    CHECK_EQ(adc_reg_size(AD7124_REG_DATA), 3);
    CHECK_EQ(adc_reg_size(AD7124_REG_CHANNEL(15)), 2);
    CHECK_EQ(adc_reg_size(AD7124_REG_CONFIG(0)), 2);
    CHECK_EQ(adc_reg_size(AD7124_REG_GAIN(7)), 3);
    CHECK_EQ(adc_reg_size(0x39), 0);
}

static void test_reset_sends_64_ones(void)
{
    setup();
    dev.regs[AD7124_REG_ADC_CONTROL] = 0x1234;
    CHECK_EQ(adc_reset(&adc), ADC_OK);
    const mock_xfer_t *x = mock_last(&dev, 0);
    CHECK(x != NULL);
    CHECK_EQ(x->n, 8);
    for (int i = 0; i < 8; i++)
        CHECK_EQ(x->tx[i], 0xFF);
    CHECK_EQ(dev.resets, 1);
    CHECK_EQ(dev.regs[AD7124_REG_ADC_CONTROL], 0);
    CHECK(dev.elapsed_us >= 1000);
}

static void test_read_id_bytes(void)
{
    setup();
    uint32_t id = 0;
    CHECK_EQ(adc_read_reg(&adc, AD7124_REG_ID, &id), ADC_OK);
    const mock_xfer_t *x = mock_last(&dev, 0);
    CHECK_EQ(x->n, 2);
    CHECK_EQ(x->tx[0], 0x45);           /* read, address 5 */
    CHECK_EQ(id, 0x14);
    CHECK_EQ(adc_probe(&adc), ADC_OK);
    CHECK_EQ(adc.id, 0x14);
}

static void test_probe_rejects_wrong_part(void)
{
    setup();
    dev.id_value = 0x04;                 /* the four channel part */
    mock_power_on(&dev);
    CHECK_EQ(adc_probe(&adc), ADC_ERR_ID);
    dev.id_value = 0xFF;                 /* nothing there, MISO floating high */
    mock_power_on(&dev);
    CHECK_EQ(adc_probe(&adc), ADC_ERR_ID);
}

static void test_write_bytes_are_msb_first(void)
{
    setup();
    CHECK_EQ(adc_write_reg(&adc, AD7124_REG_FILTER(0), 0x060008), ADC_OK);
    const mock_xfer_t *x = mock_last(&dev, 0);
    CHECK_EQ(x->n, 4);
    CHECK_EQ(x->tx[0], 0x21);
    CHECK_EQ(x->tx[1], 0x06);
    CHECK_EQ(x->tx[2], 0x00);
    CHECK_EQ(x->tx[3], 0x08);
    CHECK_EQ(dev.regs[0x21], 0x060008);
}

static void test_write_rejects_bad_arguments(void)
{
    setup();
    CHECK_EQ(adc_write_reg(&adc, AD7124_REG_DATA, 0), ADC_ERR_ARG);
    CHECK_EQ(adc_write_reg(&adc, AD7124_REG_ID, 0), ADC_ERR_ARG);
    CHECK_EQ(adc_write_reg(&adc, AD7124_REG_CHANNEL(0), 0x10000), ADC_ERR_ARG);
    CHECK_EQ(adc_write_reg(&adc, 0x3A, 0), ADC_ERR_ARG);
    CHECK_EQ(dev.log_count, 0);          /* nothing reached the bus */
}

static void test_configure_writes_and_verifies(void)
{
    setup();
    adc_config_t cfg = {8, 0, 1};
    CHECK_EQ(adc_configure(&adc, &cfg), ADC_OK);
    CHECK_EQ(dev.regs[AD7124_REG_CHANNEL(0)], 0x8001);   /* enable, AIN0-AIN1 */
    CHECK_EQ(dev.regs[AD7124_REG_CONFIG(0)], 0x09E0);    /* bipolar, buffers, PGA 1 */
    CHECK_EQ(dev.regs[AD7124_REG_FILTER(0)], 0x000008);  /* sinc4, FS 8 */
    CHECK_EQ(dev.regs[AD7124_REG_ADC_CONTROL], 0x04C0);  /* status, full power, continuous */
    CHECK_EQ(dev.protocol_errors, 0);
    /* Ten transactions: five writes, each read back. */
    CHECK_EQ(dev.log_count, 10);
}

static void test_configure_detects_readback_mismatch(void)
{
    setup();
    /* A device that acknowledges writes but keeps its old values, which is
     * what a part held in reset or a miswired MOSI looks like. */
    adc_config_t cfg = {8, 0, 1};
    dev.ignore_writes = true;
    CHECK_EQ(adc_configure(&adc, &cfg), ADC_ERR_VERIFY);
    CHECK_EQ(dev.log_count, 2);          /* stopped at the first mismatch */
}

static void test_bus_failure_is_reported(void)
{
    setup();
    dev.fail_bus_after = 0;
    uint32_t v = 0;
    CHECK_EQ(adc_read_reg(&adc, AD7124_REG_ID, &v), ADC_ERR_BUS);
    CHECK_EQ(adc_write_reg(&adc, AD7124_REG_FILTER(0), 8), ADC_ERR_BUS);
    CHECK_EQ(adc_reset(&adc), ADC_ERR_BUS);
    adc_sample_t s;
    CHECK_EQ(adc_read_sample(&adc, &s), ADC_ERR_BUS);
}

static bool fixed_source(void *ctx, int32_t *code)
{
    *code = *(int32_t *)ctx;
    return true;
}

static void test_read_sample_signs_and_status(void)
{
    setup();
    int32_t value = -1234567;
    dev.next_code = fixed_source;
    dev.source_ctx = &value;
    adc_config_t cfg = {8, 0, 1};
    CHECK_EQ(adc_configure(&adc, &cfg), ADC_OK);
    adc_sample_t s;
    CHECK_EQ(adc_wait_ready(&adc), ADC_OK);
    CHECK_EQ(adc_read_sample(&adc, &s), ADC_OK);
    CHECK_EQ(s.code, -1234567);
    CHECK_EQ(s.status & AD7124_STATUS_NRDY, 0);
    const mock_xfer_t *x = mock_last(&dev, 0);
    CHECK_EQ(x->n, 5);                   /* comms, 3 data, status */
    CHECK_EQ(x->tx[0], 0x42);

    value = 0x7FFFFF;
    CHECK_EQ(adc_wait_ready(&adc), ADC_OK);
    CHECK_EQ(adc_read_sample(&adc, &s), ADC_OK);
    CHECK_EQ(s.code, 0x7FFFFF);
    value = -0x800000;
    CHECK_EQ(adc_wait_ready(&adc), ADC_OK);
    CHECK_EQ(adc_read_sample(&adc, &s), ADC_OK);
    CHECK_EQ(s.code, -0x800000);

    dev.error_flag = true;
    CHECK_EQ(adc_wait_ready(&adc), ADC_OK);
    CHECK_EQ(adc_read_sample(&adc, &s), ADC_ERR_DEVICE);
    CHECK(s.status & AD7124_STATUS_ERROR);
    CHECK_EQ(adc.device_errors, 1);
}

static void test_wait_ready_times_out(void)
{
    setup();
    dev.stuck_not_ready = true;
    adc.ready_poll_limit = 50;
    CHECK_EQ(adc_wait_ready(&adc), ADC_ERR_TIMEOUT);
    CHECK_EQ(adc.timeouts, 1);
    CHECK_EQ(dev.elapsed_us, 500);
}

static void test_offset_binary(void)
{
    CHECK_EQ(adc_offset_binary_to_signed(0x800000), 0);
    CHECK_EQ(adc_offset_binary_to_signed(0xFFFFFF), 0x7FFFFF);
    CHECK_EQ(adc_offset_binary_to_signed(0x000000), -0x800000);
    CHECK_EQ(adc_offset_binary_to_signed(0x7FFFFF), -1);
}

static void test_output_data_rate(void)
{
    CHECK_EQ(adc_odr_mhz(8), 2400000);       /* 2400 SPS, the nominal setting */
    CHECK_EQ(adc_odr_mhz(1), 19200000);
    CHECK_EQ(adc_odr_mhz(2047), 9380);
    CHECK_EQ(adc_odr_mhz(0), 0);
    CHECK_EQ(adc_fs_for_odr(2400), 8);
    CHECK_EQ(adc_fs_for_odr(2000), 10);      /* 1920 SPS, at or below */
    CHECK_EQ(adc_fs_for_odr(100000), 1);
    CHECK_EQ(adc_fs_for_odr(1), 2047);
}

void test_adc_spi(void)
{
    RUN(test_register_sizes_match_mock);
    RUN(test_reset_sends_64_ones);
    RUN(test_read_id_bytes);
    RUN(test_probe_rejects_wrong_part);
    RUN(test_write_bytes_are_msb_first);
    RUN(test_write_rejects_bad_arguments);
    RUN(test_configure_writes_and_verifies);
    RUN(test_configure_detects_readback_mismatch);
    RUN(test_bus_failure_is_reported);
    RUN(test_read_sample_signs_and_status);
    RUN(test_wait_ready_times_out);
    RUN(test_offset_binary);
    RUN(test_output_data_rate);
}
