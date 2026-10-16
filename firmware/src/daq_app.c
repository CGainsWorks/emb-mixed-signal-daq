/*
 * The acquisition application. See daq_app.h.
 */
#include "daq_app.h"

#include <string.h>

const uint16_t daq_gain_nominal[DAQ_GAIN_COUNT] = {1, 8, 32, 128};

/* The board routes the front end output to AIN0 / AIN1. */
#define AIN_POS 0u
#define AIN_NEG 1u

void daq_init(daq_t *d, const hal_spi_t *spi, const hal_frontend_t *fe,
              void *link_ctx, int (*link_write)(void *, const uint8_t *, size_t))
{
    memset(d, 0, sizeof *d);
    adc_init(&d->adc, spi);
    sampler_init(&d->sampler, &d->adc);
    hl_init(&d->link, link_ctx, link_write);
    d->fe = *fe;
    for (unsigned g = 0; g < DAQ_GAIN_COUNT; g++)
        cal_identity(&d->coeffs[g]);
}

int64_t daq_full_scale_nv(unsigned gain_index)
{
    if (gain_index >= DAQ_GAIN_COUNT)
        return 0;
    return DAQ_VREF_NV / daq_gain_nominal[gain_index];
}

daq_status_t daq_start(daq_t *d, const daq_settings_t *s)
{
    adc_status_t st;
    if (s == NULL || s->gain_index >= DAQ_GAIN_COUNT || s->odr_hz == 0)
        return DAQ_ERR_ARG;
    d->settings = *s;
    adc_config_t cfg = {adc_fs_for_odr(s->odr_hz), AIN_POS, AIN_NEG};

    if ((st = adc_reset(&d->adc)) != ADC_OK ||
        (st = adc_probe(&d->adc)) != ADC_OK ||
        (st = adc_configure(&d->adc, &cfg)) != ADC_OK) {
        d->last_adc_error = st;
        return DAQ_ERR_ADC;
    }
    d->fe.select_gain(d->fe.ctx, s->gain_index);
    d->fe.select_input(d->fe.ctx, INPUT_SIGNAL);
    return DAQ_OK;
}

static daq_status_t settle_and_average(daq_t *d, uint32_t n, int64_t *mean_q8)
{
    int32_t chunk[32];
    uint32_t discard = DAQ_SETTLE_SAMPLES;
    while (discard > 0) {
        uint32_t take = discard;
        if (sampler_capture(&d->sampler, chunk, take) != take)
            return DAQ_ERR_CAPTURE;
        discard -= take;
    }
    cal_accumulator_t acc;
    cal_acc_reset(&acc);
    while (n > 0) {
        uint32_t take = n < 32u ? n : 32u;
        if (sampler_capture(&d->sampler, chunk, take) != take)
            return DAQ_ERR_CAPTURE;
        for (uint32_t i = 0; i < take; i++)
            cal_acc_add(&acc, chunk[i]);
        n -= take;
    }
    return cal_acc_mean_q8(&acc, mean_q8) == CAL_OK ? DAQ_OK : DAQ_ERR_CAPTURE;
}

daq_status_t daq_calibrate(daq_t *d, int64_t vcal_nv, uint32_t n_avg)
{
    unsigned g = d->settings.gain_index;
    int64_t zero_q8 = 0;
    int64_t ref_q8 = 0;
    daq_status_t st;
    cal_coeffs_t c;

    if (n_avg == 0)
        return DAQ_ERR_ARG;
    d->fe.select_input(d->fe.ctx, INPUT_SHORT);
    st = settle_and_average(d, n_avg, &zero_q8);
    if (st == DAQ_OK) {
        d->fe.select_input(d->fe.ctx, INPUT_CAL_REF);
        st = settle_and_average(d, n_avg, &ref_q8);
    }
    d->fe.select_input(d->fe.ctx, INPUT_SIGNAL);
    if (st != DAQ_OK)
        return st;
    if (cal_compute(zero_q8, ref_q8, vcal_nv, daq_full_scale_nv(g), &c) != CAL_OK)
        return DAQ_ERR_CAL;
    d->coeffs[g] = c;
    d->calibrated[g] = true;

    int32_t words[5] = {
        (int32_t)(uint32_t)((uint64_t)c.offset_q8 & 0xFFFFFFFFu),
        (int32_t)(c.offset_q8 >> 32),
        (int32_t)(uint32_t)((uint64_t)c.gain_q29 & 0xFFFFFFFFu),
        (int32_t)(c.gain_q29 >> 32),
        (int32_t)g,
    };
    return hl_send(&d->link, HL_FRAME_COEFFS, words, 5) == 0 ? DAQ_OK : DAQ_ERR_LINK;
}

uint32_t daq_service(daq_t *d)
{
    int32_t cal[HL_MAX_WORDS];
    int32_t raw[HL_MAX_WORDS];
    uint32_t n = 0;
    uint32_t sent = 0;
    sample_t s;
    const cal_coeffs_t *c = &d->coeffs[d->settings.gain_index];

    while (sampler_pop(&d->sampler, &s)) {
        raw[n] = s.code;
        cal[n] = cal_apply(s.code, c);
        if (++n == HL_MAX_WORDS) {
            if (d->settings.send_raw)
                hl_send(&d->link, HL_FRAME_RAW, raw, n);
            hl_send(&d->link, HL_FRAME_SAMPLES, cal, n);
            sent += n;
            n = 0;
        }
    }
    if (n > 0) {
        if (d->settings.send_raw)
            hl_send(&d->link, HL_FRAME_RAW, raw, n);
        hl_send(&d->link, HL_FRAME_SAMPLES, cal, n);
        sent += n;
    }
    return sent;
}

daq_status_t daq_send_status(daq_t *d)
{
    int32_t w[5] = {
        (int32_t)d->sampler.produced, (int32_t)d->sampler.overflows,
        (int32_t)d->sampler.device_errors, (int32_t)d->sampler.bus_errors,
        (int32_t)d->adc.timeouts,
    };
    return hl_send(&d->link, HL_FRAME_STATUS, w, 5) == 0 ? DAQ_OK : DAQ_ERR_LINK;
}
