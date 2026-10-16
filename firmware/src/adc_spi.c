/*
 * AD7124-8 class converter driver. See adc_spi.h for the scope and the
 * caveat that the register map has only been exercised against a mock.
 */
#include "adc_spi.h"

#include <string.h>

/* Time the part needs after a serial reset before it accepts commands. The
 * datasheet figure should be confirmed on bring-up; this is generous. */
#define RESET_SETTLE_US 2000u
#define READY_POLL_INTERVAL_US 10u
#define DEFAULT_READY_POLLS 100000u

void adc_init(adc_t *adc, const hal_spi_t *hal)
{
    memset(adc, 0, sizeof *adc);
    adc->hal = *hal;
    adc->ready_poll_limit = DEFAULT_READY_POLLS;
}

unsigned adc_reg_size(uint8_t reg)
{
    if (reg == AD7124_REG_STATUS || reg == AD7124_REG_ID ||
        reg == AD7124_REG_MCLK_COUNT)
        return 1;
    if (reg == AD7124_REG_ADC_CONTROL || reg == AD7124_REG_IO_CONTROL_2)
        return 2;
    if (reg == AD7124_REG_DATA || reg == AD7124_REG_IO_CONTROL_1 ||
        reg == AD7124_REG_ERROR || reg == AD7124_REG_ERROR_EN)
        return 3;
    if (reg >= AD7124_REG_CHANNEL(0) && reg < AD7124_REG_FILTER(0))
        return 2;   /* CHANNEL_0..15 and CONFIG_0..7 */
    if (reg >= AD7124_REG_FILTER(0) && reg < AD7124_REG_COUNT)
        return 3;   /* FILTER, OFFSET and GAIN */
    return 0;
}

static int xfer(adc_t *adc, const uint8_t *tx, uint8_t *rx, size_t n)
{
    return adc->hal.xfer(adc->hal.ctx, tx, rx, n);
}

adc_status_t adc_reset(adc_t *adc)
{
    /* 64 consecutive ones on DIN reset the serial interface and every
     * register. */
    uint8_t ones[8];
    memset(ones, 0xFF, sizeof ones);
    if (xfer(adc, ones, NULL, sizeof ones) != 0)
        return ADC_ERR_BUS;
    adc->hal.delay_us(adc->hal.ctx, RESET_SETTLE_US);
    return ADC_OK;
}

adc_status_t adc_read_reg(adc_t *adc, uint8_t reg, uint32_t *value)
{
    unsigned size = adc_reg_size(reg);
    uint8_t tx[4] = {0};
    uint8_t rx[4] = {0};
    if (size == 0 || value == NULL)
        return ADC_ERR_ARG;
    tx[0] = (uint8_t)(AD7124_COMMS_READ | (reg & AD7124_ADDR_MASK));
    if (xfer(adc, tx, rx, size + 1u) != 0)
        return ADC_ERR_BUS;
    *value = 0;
    for (unsigned i = 1; i <= size; i++)
        *value = (*value << 8) | rx[i];
    return ADC_OK;
}

adc_status_t adc_write_reg(adc_t *adc, uint8_t reg, uint32_t value)
{
    unsigned size = adc_reg_size(reg);
    uint8_t tx[4];
    /* STATUS, DATA, ID and ERROR are read only. */
    if (size == 0 || reg == AD7124_REG_STATUS || reg == AD7124_REG_DATA ||
        reg == AD7124_REG_ID || reg == AD7124_REG_ERROR)
        return ADC_ERR_ARG;
    if (size < 4 && (value >> (8u * size)) != 0)
        return ADC_ERR_ARG;
    tx[0] = (uint8_t)(reg & AD7124_ADDR_MASK);
    for (unsigned i = 0; i < size; i++)
        tx[1 + i] = (uint8_t)(value >> (8u * (size - 1u - i)));
    return xfer(adc, tx, NULL, size + 1u) == 0 ? ADC_OK : ADC_ERR_BUS;
}

adc_status_t adc_write_verify(adc_t *adc, uint8_t reg, uint32_t value)
{
    uint32_t back = 0;
    adc_status_t st = adc_write_reg(adc, reg, value);
    if (st != ADC_OK)
        return st;
    st = adc_read_reg(adc, reg, &back);
    if (st != ADC_OK)
        return st;
    return back == value ? ADC_OK : ADC_ERR_VERIFY;
}

adc_status_t adc_probe(adc_t *adc)
{
    uint32_t id = 0;
    adc_status_t st = adc_read_reg(adc, AD7124_REG_ID, &id);
    if (st != ADC_OK)
        return st;
    adc->id = (uint8_t)id;
    /* The AD7124-8 reports 0x1X, the low nibble being the silicon revision.
     * Anything else is the wrong part, or no part and a floating MISO. */
    return (id & 0xF0u) == 0x10u ? ADC_OK : ADC_ERR_ID;
}

uint32_t adc_odr_mhz(uint16_t fs)
{
    if (fs == 0 || fs > AD7124_FILTER_FS_MASK)
        return 0;
    uint64_t num = (uint64_t)AD7124_FCLK_FULL_POWER * 1000u;
    uint64_t den = 32u * (uint64_t)fs;
    return (uint32_t)((num + den / 2u) / den);
}

uint16_t adc_fs_for_odr(uint32_t odr_hz)
{
    if (odr_hz == 0)
        return AD7124_FILTER_FS_MASK;
    uint32_t den = 32u * odr_hz;
    uint32_t fs = (AD7124_FCLK_FULL_POWER + den - 1u) / den;
    if (fs < 1u)
        fs = 1u;
    if (fs > AD7124_FILTER_FS_MASK)
        fs = AD7124_FILTER_FS_MASK;
    return (uint16_t)fs;
}

adc_status_t adc_configure(adc_t *adc, const adc_config_t *cfg)
{
    adc_status_t st;
    if (cfg == NULL || cfg->fs == 0 || cfg->fs > AD7124_FILTER_FS_MASK ||
        cfg->ainp > 31u || cfg->ainm > 31u)
        return ADC_ERR_ARG;

    const uint32_t standby = AD7124_CTRL_DATA_STATUS | AD7124_CTRL_POWER_FULL |
                             (AD7124_MODE_STANDBY << AD7124_CTRL_MODE_SHIFT);
    const uint32_t channel = AD7124_CH_ENABLE | (0u << AD7124_CH_SETUP_SHIFT) |
                             ((uint32_t)cfg->ainp << AD7124_CH_AINP_SHIFT) |
                             cfg->ainm;
    /* Bipolar, all four buffers on, external REFIN1, PGA = 1. */
    const uint32_t config = AD7124_CFG_BIPOLAR | AD7124_CFG_REF_BUFP |
                            AD7124_CFG_REF_BUFM | AD7124_CFG_AIN_BUFP |
                            AD7124_CFG_AIN_BUFM;
    const uint32_t filter = (0u << AD7124_FILTER_TYPE_SHIFT) | cfg->fs;
    const uint32_t run = AD7124_CTRL_DATA_STATUS | AD7124_CTRL_POWER_FULL |
                         (AD7124_MODE_CONTINUOUS << AD7124_CTRL_MODE_SHIFT);

    if ((st = adc_write_verify(adc, AD7124_REG_ADC_CONTROL, standby)) != ADC_OK)
        return st;
    if ((st = adc_write_verify(adc, AD7124_REG_CHANNEL(0), channel)) != ADC_OK)
        return st;
    if ((st = adc_write_verify(adc, AD7124_REG_CONFIG(0), config)) != ADC_OK)
        return st;
    if ((st = adc_write_verify(adc, AD7124_REG_FILTER(0), filter)) != ADC_OK)
        return st;
    return adc_write_verify(adc, AD7124_REG_ADC_CONTROL, run);
}

adc_status_t adc_wait_ready(adc_t *adc)
{
    for (uint32_t i = 0; i < adc->ready_poll_limit; i++) {
        if (adc->hal.data_ready(adc->hal.ctx))
            return ADC_OK;
        adc->hal.delay_us(adc->hal.ctx, READY_POLL_INTERVAL_US);
    }
    adc->timeouts++;
    return ADC_ERR_TIMEOUT;
}

int32_t adc_offset_binary_to_signed(uint32_t raw)
{
    return (int32_t)(raw & 0xFFFFFFu) - 0x800000;
}

adc_status_t adc_read_sample(adc_t *adc, adc_sample_t *out)
{
    /* With DATA_STATUS set the status register follows the 24 data bits, so
     * every sample carries its own error flag and channel number. */
    uint8_t tx[5] = {AD7124_COMMS_READ | AD7124_REG_DATA, 0, 0, 0, 0};
    uint8_t rx[5] = {0};
    if (out == NULL)
        return ADC_ERR_ARG;
    if (xfer(adc, tx, rx, sizeof tx) != 0)
        return ADC_ERR_BUS;
    uint32_t raw = ((uint32_t)rx[1] << 16) | ((uint32_t)rx[2] << 8) | rx[3];
    out->code = adc_offset_binary_to_signed(raw);
    out->status = rx[4];
    if (out->status & AD7124_STATUS_ERROR) {
        adc->device_errors++;
        return ADC_ERR_DEVICE;
    }
    return ADC_OK;
}
