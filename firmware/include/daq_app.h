/*
 * The acquisition application: bring-up, calibration and streaming.
 *
 * Board independent. A target build supplies the two HAL structures and
 * calls daq_service() from its main loop and sampler_on_ready() from the
 * DOUT/RDY interrupt; the host build in firmware/host does the same against
 * the mocked converter.
 */
#ifndef DAQ_APP_H
#define DAQ_APP_H

#include <stdbool.h>
#include <stdint.h>

#include "adc_spi.h"
#include "calibration.h"
#include "hal_spi.h"
#include "host_link.h"
#include "sampling_engine.h"

#define DAQ_GAIN_COUNT 4u
#define DAQ_VREF_NV 2500000000LL
/* Conversions discarded after the input or gain changes. A sinc4 filter
 * needs four output periods to flush the old input completely. */
#define DAQ_SETTLE_SAMPLES 4u

extern const uint16_t daq_gain_nominal[DAQ_GAIN_COUNT];   /* 1, 8, 32, 128 */

typedef enum {
    DAQ_OK = 0,
    DAQ_ERR_ADC = -1,
    DAQ_ERR_CAPTURE = -2,
    DAQ_ERR_CAL = -3,
    DAQ_ERR_ARG = -4,
    DAQ_ERR_LINK = -5
} daq_status_t;

typedef struct {
    uint32_t odr_hz;
    unsigned gain_index;
    bool send_raw;            /* stream raw codes as well as calibrated */
} daq_settings_t;

typedef struct {
    adc_t adc;
    sampler_t sampler;
    host_link_t link;
    hal_frontend_t fe;
    daq_settings_t settings;
    cal_coeffs_t coeffs[DAQ_GAIN_COUNT];
    bool calibrated[DAQ_GAIN_COUNT];
    adc_status_t last_adc_error;
} daq_t;

void daq_init(daq_t *d, const hal_spi_t *spi, const hal_frontend_t *fe,
              void *link_ctx, int (*link_write)(void *, const uint8_t *, size_t));
daq_status_t daq_start(daq_t *d, const daq_settings_t *s);
int64_t daq_full_scale_nv(unsigned gain_index);
/* Zero and reference calibration of the current gain. vcal_nv is the
 * calibrator's setting; n_avg conversions are averaged at each point. */
daq_status_t daq_calibrate(daq_t *d, int64_t vcal_nv, uint32_t n_avg);
/* Drain the ring, calibrate and send. Returns samples sent. */
uint32_t daq_service(daq_t *d);
daq_status_t daq_send_status(daq_t *d);

#endif
