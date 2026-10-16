/*
 * Driver for an AD7124-8 class 24-bit sigma-delta converter over SPI.
 *
 * The register map, the communications register format, the reset sequence
 * and the output data rate formula follow the public AD7124-8 datasheet.
 * None of it has been exercised against a real part: the tests run it
 * against a mocked device that implements the same map. See STATUS.md.
 *
 * The converter's internal PGA is left at 1. Gain is set in the analogue
 * front end, where it can be had for less noise (see the noise budget).
 */
#ifndef ADC_SPI_H
#define ADC_SPI_H

#include <stdint.h>

#include "hal_spi.h"

/* Communications register: bit 7 WEN must be 0, bit 6 is read, 5:0 address. */
#define AD7124_COMMS_READ 0x40u
#define AD7124_ADDR_MASK 0x3Fu

/* Register addresses. */
#define AD7124_REG_STATUS 0x00u     /* read: status; write: comms */
#define AD7124_REG_ADC_CONTROL 0x01u
#define AD7124_REG_DATA 0x02u
#define AD7124_REG_IO_CONTROL_1 0x03u
#define AD7124_REG_IO_CONTROL_2 0x04u
#define AD7124_REG_ID 0x05u
#define AD7124_REG_ERROR 0x06u
#define AD7124_REG_ERROR_EN 0x07u
#define AD7124_REG_MCLK_COUNT 0x08u
#define AD7124_REG_CHANNEL(n) (0x09u + (n))   /* 0..15 */
#define AD7124_REG_CONFIG(n) (0x19u + (n))    /* 0..7 */
#define AD7124_REG_FILTER(n) (0x21u + (n))    /* 0..7 */
#define AD7124_REG_OFFSET(n) (0x29u + (n))    /* 0..7 */
#define AD7124_REG_GAIN(n) (0x31u + (n))      /* 0..7 */
#define AD7124_REG_COUNT 0x39u

/* STATUS bits. RDY is active low. */
#define AD7124_STATUS_NRDY 0x80u
#define AD7124_STATUS_ERROR 0x40u
#define AD7124_STATUS_POR 0x10u
#define AD7124_STATUS_CH_MASK 0x0Fu

/* ADC_CONTROL fields. */
#define AD7124_CTRL_DATA_STATUS (1u << 10)
#define AD7124_CTRL_CS_EN (1u << 9)
#define AD7124_CTRL_REF_EN (1u << 8)
#define AD7124_CTRL_POWER_FULL (3u << 6)
#define AD7124_CTRL_MODE_SHIFT 2u
#define AD7124_CTRL_MODE_MASK (0xFu << 2)
#define AD7124_MODE_CONTINUOUS 0x0u
#define AD7124_MODE_SINGLE 0x1u
#define AD7124_MODE_STANDBY 0x2u
#define AD7124_MODE_IDLE 0x4u

/* CHANNEL_n fields. */
#define AD7124_CH_ENABLE (1u << 15)
#define AD7124_CH_SETUP_SHIFT 12u
#define AD7124_CH_AINP_SHIFT 5u

/* CONFIG_n fields. */
#define AD7124_CFG_BIPOLAR (1u << 11)
#define AD7124_CFG_REF_BUFP (1u << 8)
#define AD7124_CFG_REF_BUFM (1u << 7)
#define AD7124_CFG_AIN_BUFP (1u << 6)
#define AD7124_CFG_AIN_BUFM (1u << 5)
#define AD7124_CFG_REF_SEL_SHIFT 3u   /* 00 REFIN1 */
#define AD7124_CFG_PGA_MASK 0x7u

/* FILTER_n fields. */
#define AD7124_FILTER_TYPE_SHIFT 21u  /* 000 sinc4 */
#define AD7124_FILTER_FS_MASK 0x7FFu

/* Full power mode master clock and the sinc4 output data rate:
 * ODR = f_CLK / (32 * FS). */
#define AD7124_FCLK_FULL_POWER 614400u

typedef enum {
    ADC_OK = 0,
    ADC_ERR_BUS = -1,
    ADC_ERR_ID = -2,
    ADC_ERR_VERIFY = -3,
    ADC_ERR_TIMEOUT = -4,
    ADC_ERR_ARG = -5,
    ADC_ERR_DEVICE = -6
} adc_status_t;

typedef struct {
    uint16_t fs;          /* filter word, 1..2047 */
    uint8_t ainp;         /* analogue input pins */
    uint8_t ainm;
} adc_config_t;

typedef struct {
    hal_spi_t hal;
    uint8_t id;
    uint32_t timeouts;
    uint32_t device_errors;
    uint32_t ready_poll_limit;   /* polls of data_ready before a timeout */
} adc_t;

typedef struct {
    int32_t code;         /* signed 24-bit, sign extended */
    uint8_t status;
} adc_sample_t;

void adc_init(adc_t *adc, const hal_spi_t *hal);
adc_status_t adc_reset(adc_t *adc);
adc_status_t adc_read_reg(adc_t *adc, uint8_t reg, uint32_t *value);
adc_status_t adc_write_reg(adc_t *adc, uint8_t reg, uint32_t value);
adc_status_t adc_write_verify(adc_t *adc, uint8_t reg, uint32_t value);
adc_status_t adc_probe(adc_t *adc);
adc_status_t adc_configure(adc_t *adc, const adc_config_t *cfg);
adc_status_t adc_wait_ready(adc_t *adc);
adc_status_t adc_read_sample(adc_t *adc, adc_sample_t *out);

/* Size in bytes of register reg, 0 for an invalid address. */
unsigned adc_reg_size(uint8_t reg);
/* Output data rate in millihertz for a filter word and the filter word that
 * gives the closest rate at or below the request. */
uint32_t adc_odr_mhz(uint16_t fs);
uint16_t adc_fs_for_odr(uint32_t odr_hz);
/* Offset binary (bipolar coding) to signed. */
int32_t adc_offset_binary_to_signed(uint32_t raw);

#endif
