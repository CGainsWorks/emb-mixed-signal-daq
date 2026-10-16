/*
 * Application tests: bring-up, the calibration sequence and its input
 * switching and streaming through to frames.
 */
#include <string.h>

#include "daq_app.h"
#include "mock_ad7124.h"
#include "unit.h"

typedef struct {
    daq_input_t input;
    unsigned gain;
    unsigned switches;
    int32_t level[3];       /* code each input produces */
    uint8_t out[16384];
    size_t out_len;
} board_t;

static mock_ad7124_t dev;
static board_t board;
static daq_t daq;

static bool source(void *ctx, int32_t *code)
{
    board_t *b = ctx;
    *code = b->level[b->input];
    return true;
}

static void sel_input(void *ctx, daq_input_t in)
{
    board_t *b = ctx;
    b->input = in;
    b->switches++;
}

static void sel_gain(void *ctx, unsigned g) { ((board_t *)ctx)->gain = g; }

static int link_write(void *ctx, const uint8_t *d, size_t n)
{
    board_t *b = ctx;
    if (b->out_len + n > sizeof b->out)
        return -1;
    memcpy(b->out + b->out_len, d, n);
    b->out_len += n;
    return 0;
}

static void setup(void)
{
    memset(&board, 0, sizeof board);
    mock_init(&dev);
    dev.next_code = source;
    dev.source_ctx = &board;
    hal_spi_t h = mock_hal(&dev);
    hal_frontend_t fe = {&board, sel_input, sel_gain};
    daq_init(&daq, &h, &fe, &board, link_write);
}

static void test_start_configures_and_selects(void)
{
    setup();
    daq_settings_t s = {2400, 3, false};
    CHECK_EQ(daq_start(&daq, &s), DAQ_OK);
    CHECK_EQ(dev.resets, 1);
    CHECK_EQ(board.gain, 3);
    CHECK_EQ(board.input, INPUT_SIGNAL);
    CHECK_EQ(dev.regs[AD7124_REG_FILTER(0)], 8);
    CHECK_EQ(daq_full_scale_nv(3), 19531250);
    CHECK_EQ(daq_full_scale_nv(4), 0);
}

static void test_start_fails_cleanly_without_a_part(void)
{
    setup();
    dev.id_value = 0xFF;
    daq_settings_t s = {2400, 0, false};
    CHECK_EQ(daq_start(&daq, &s), DAQ_ERR_ADC);
    CHECK_EQ(daq.last_adc_error, ADC_ERR_ID);
    s.gain_index = 4;
    CHECK_EQ(daq_start(&daq, &s), DAQ_ERR_ARG);
}

static void test_calibration_sequence(void)
{
    setup();
    daq_settings_t s = {2400, 0, false};
    CHECK_EQ(daq_start(&daq, &s), DAQ_OK);
    /* Zero reads -1000 codes; the reference reads 0.9 of full scale plus
     * that offset, minus a 0.1 percent gain error. */
    board.level[INPUT_SHORT] = -1000;
    board.level[INPUT_CAL_REF] = -1000 + (int32_t)(0.9 * 8388608 * 0.999);
    board.level[INPUT_SIGNAL] = -1000;
    unsigned before = dev.conversions;
    CHECK_EQ(daq_calibrate(&daq, 2250000000LL, 16), DAQ_OK);
    CHECK_EQ(dev.conversions - before, 2 * (16 + DAQ_SETTLE_SAMPLES));
    CHECK_EQ(board.input, INPUT_SIGNAL);       /* left on the signal */
    CHECK(daq.calibrated[0]);
    CHECK_EQ(daq.coeffs[0].offset_q8, -256000);
    /* Gain corrects the 0.1 percent: 2^29 / 0.999, to the rounding of the
     * integer reference codes. */
    CHECK(daq.coeffs[0].gain_q29 > 537400000 && daq.coeffs[0].gain_q29 < 537450000);
    CHECK_EQ(cal_apply(-1000, &daq.coeffs[0]), 0);
    /* One coefficient frame went out. */
    CHECK_EQ(board.out_len, 6 + 20 + 2);
    CHECK_EQ(board.out[2], HL_FRAME_COEFFS);
}

static void test_calibration_failure_restores_input(void)
{
    setup();
    daq_settings_t s = {2400, 0, false};
    CHECK_EQ(daq_start(&daq, &s), DAQ_OK);
    board.level[INPUT_SHORT] = 0;
    board.level[INPUT_CAL_REF] = 0;          /* reference not connected */
    CHECK_EQ(daq_calibrate(&daq, 2250000000LL, 8), DAQ_ERR_CAL);
    CHECK_EQ(board.input, INPUT_SIGNAL);
    CHECK(!daq.calibrated[0]);
    dev.stuck_not_ready = true;
    daq.adc.ready_poll_limit = 5;
    CHECK_EQ(daq_calibrate(&daq, 2250000000LL, 8), DAQ_ERR_CAPTURE);
    CHECK_EQ(board.input, INPUT_SIGNAL);
}

static void test_streaming_frames(void)
{
    setup();
    daq_settings_t s = {2400, 0, true};
    CHECK_EQ(daq_start(&daq, &s), DAQ_OK);
    board.level[INPUT_SIGNAL] = 4096;
    for (int i = 0; i < 100; i++)
        CHECK(sampler_poll(&daq.sampler));
    CHECK_EQ(daq_service(&daq), 100);
    /* 100 samples: frames of 64 and 36, raw and calibrated for each. */
    size_t expect = 2 * (6 + 4 * 64 + 2) + 2 * (6 + 4 * 36 + 2);
    CHECK_EQ(board.out_len, expect);
    CHECK_EQ(board.out[2], HL_FRAME_RAW);
    CHECK_EQ(board.out[6], 0x00);            /* 4096 = 0x1000, little endian */
    CHECK_EQ(board.out[7], 0x10);
    size_t second = 6 + 4 * 64 + 2;
    CHECK_EQ(board.out[second + 2], HL_FRAME_SAMPLES);
    CHECK_EQ(board.out[second + 7], 0x00);   /* identity: 4096 * 256 = 0x100000 */
    CHECK_EQ(board.out[second + 8], 0x10);
    CHECK_EQ(daq_send_status(&daq), DAQ_OK);
}

void test_daq_app(void)
{
    RUN(test_start_configures_and_selects);
    RUN(test_start_fails_cleanly_without_a_part);
    RUN(test_calibration_sequence);
    RUN(test_calibration_failure_restores_input);
    RUN(test_streaming_frames);
}
