/*
 * Firmware in the loop on the host.
 *
 * Runs the real application code (daq_app, the driver, the sampling engine,
 * calibration and framing) against the mocked converter, which serves codes
 * produced by the behavioural converter model. Three code files stand for
 * the three front end inputs: a shorted input, the calibration reference and
 * the signal. The framed output is what the host capture tool would receive
 * over the serial link.
 *
 *   daq_sim GAIN_INDEX VCAL_NV N_AVG ZERO.txt CAL.txt SIGNAL.txt OUT.bin
 *
 * Exit status 0 on success. Everything printed is a summary for the log.
 */
#include <stdio.h>
#include <stdlib.h>

#include "daq_app.h"
#include "mock_ad7124.h"

typedef struct {
    int32_t *codes;
    size_t n;
    size_t pos;
} dataset_t;

typedef struct {
    dataset_t sets[3];
    daq_input_t input;
    unsigned gain_index;
    FILE *out;
} sim_t;

static int load(const char *path, dataset_t *d)
{
    FILE *f = fopen(path, "r");
    long v;
    size_t cap = 1024;
    if (!f)
        return -1;
    d->codes = malloc(cap * sizeof *d->codes);
    d->n = d->pos = 0;
    while (d->codes && fscanf(f, "%ld", &v) == 1) {
        if (d->n == cap) {
            int32_t *p = realloc(d->codes, 2 * cap * sizeof *p);
            if (!p)
                break;
            d->codes = p;
            cap *= 2;
        }
        d->codes[d->n++] = (int32_t)v;
    }
    fclose(f);
    return d->codes ? 0 : -1;
}

static bool next_code(void *ctx, int32_t *code)
{
    sim_t *s = ctx;
    dataset_t *d = &s->sets[s->input];
    if (d->pos >= d->n)
        return false;
    *code = d->codes[d->pos++];
    return true;
}

static void select_input(void *ctx, daq_input_t in) { ((sim_t *)ctx)->input = in; }
static void select_gain(void *ctx, unsigned g) { ((sim_t *)ctx)->gain_index = g; }

static int write_out(void *ctx, const uint8_t *data, size_t n)
{
    sim_t *s = ctx;
    return fwrite(data, 1, n, s->out) == n ? 0 : -1;
}

int main(int argc, char **argv)
{
    if (argc != 8) {
        fprintf(stderr, "usage: %s GAIN_INDEX VCAL_NV N_AVG ZERO CAL SIGNAL OUT\n", argv[0]);
        return 2;
    }
    sim_t sim = {0};
    unsigned gain_index = (unsigned)strtoul(argv[1], NULL, 10);
    long long vcal_nv = strtoll(argv[2], NULL, 10);
    uint32_t n_avg = (uint32_t)strtoul(argv[3], NULL, 10);
    if (load(argv[4], &sim.sets[INPUT_SHORT]) || load(argv[5], &sim.sets[INPUT_CAL_REF]) ||
        load(argv[6], &sim.sets[INPUT_SIGNAL])) {
        fprintf(stderr, "cannot read code files\n");
        return 2;
    }
    sim.out = fopen(argv[7], "wb");
    if (!sim.out) {
        fprintf(stderr, "cannot open %s\n", argv[7]);
        return 2;
    }

    mock_ad7124_t dev;
    mock_init(&dev);
    dev.next_code = next_code;
    dev.source_ctx = &sim;
    hal_spi_t spi = mock_hal(&dev);
    hal_frontend_t fe = {&sim, select_input, select_gain};

    daq_t daq;
    daq_init(&daq, &spi, &fe, &sim, write_out);
    daq_settings_t st = {2400u, gain_index, true};
    /* The converter only starts converting once configured, so the input
     * selected at power up must not be consumed before then. */
    sim.input = INPUT_SIGNAL;
    if (daq_start(&daq, &st) != DAQ_OK) {
        fprintf(stderr, "start failed: adc status %d\n", daq.last_adc_error);
        return 1;
    }
    if (daq_calibrate(&daq, vcal_nv, n_avg) != DAQ_OK) {
        fprintf(stderr, "calibration failed\n");
        return 1;
    }
    /* Stream: the poll stands in for the DOUT/RDY interrupt; the service
     * call is the main loop. Interleaving them every 32 samples keeps the
     * 256 entry ring from overflowing, which is checked below. */
    uint32_t polled = 0;
    while (sampler_poll(&daq.sampler)) {
        if (++polled % 32u == 0)
            daq_service(&daq);
    }
    daq_service(&daq);
    daq_send_status(&daq);
    fclose(sim.out);

    printf("gain index %u, offset_q8 %lld, gain_q29 %lld\n", gain_index,
           (long long)daq.coeffs[gain_index].offset_q8,
           (long long)daq.coeffs[gain_index].gain_q29);
    printf("conversions %u, streamed %u, overflows %u, device errors %u, "
           "frames %u, protocol errors %u\n",
           dev.conversions, (unsigned)polled, (unsigned)daq.sampler.overflows,
           (unsigned)daq.sampler.device_errors, (unsigned)daq.link.frames_sent,
           dev.protocol_errors);
    for (int i = 0; i < 3; i++)
        free(sim.sets[i].codes);
    return (daq.sampler.overflows || dev.protocol_errors) ? 1 : 0;
}
