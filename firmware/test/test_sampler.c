/*
 * Sampling engine tests: ordering, numbering, overflow accounting and the
 * error paths, driven through the mocked converter.
 */
#include "mock_ad7124.h"
#include "sampling_engine.h"
#include "unit.h"

static mock_ad7124_t dev;
static adc_t adc;
static sampler_t smp;
static int32_t counter;

static bool counting_source(void *ctx, int32_t *code)
{
    (void)ctx;
    *code = counter++;
    return true;
}

static void setup(void)
{
    mock_init(&dev);
    dev.next_code = counting_source;
    counter = -100;
    hal_spi_t h = mock_hal(&dev);
    adc_init(&adc, &h);
    adc_config_t cfg = {8, 0, 1};
    adc_configure(&adc, &cfg);
    sampler_init(&smp, &adc);
}

static void test_samples_arrive_in_order_and_numbered(void)
{
    setup();
    for (int i = 0; i < 10; i++)
        CHECK(sampler_poll(&smp));
    CHECK_EQ(sampler_count(&smp), 10);
    sample_t s;
    for (int i = 0; i < 10; i++) {
        CHECK(sampler_pop(&smp, &s));
        CHECK_EQ(s.code, -100 + i);
        CHECK_EQ(s.seq, i);
    }
    CHECK(!sampler_pop(&smp, &s));
}

static void test_overflow_is_counted_and_visible_in_sequence(void)
{
    setup();
    for (unsigned i = 0; i < SAMPLER_RING_SIZE; i++)
        CHECK(sampler_on_ready(&smp));
    /* Ring full: the next three conversions are lost and counted. */
    dev.ready = false;
    for (int i = 0; i < 3; i++) {
        CHECK(sampler_poll(&smp) == false);
    }
    CHECK_EQ(smp.overflows, 3);
    sample_t s;
    CHECK(sampler_pop(&smp, &s));
    CHECK_EQ(s.seq, 0);
    CHECK(sampler_poll(&smp));
    /* Drain: the last sample's number jumps by the three lost ones. */
    uint32_t last = 0;
    while (sampler_pop(&smp, &s))
        last = s.seq;
    CHECK_EQ(last, SAMPLER_RING_SIZE + 3);
    CHECK_EQ(smp.produced, SAMPLER_RING_SIZE + 4);
}

static void test_indices_wrap_cleanly(void)
{
    setup();
    smp.head = smp.tail = 0xFFFFFFF0u;   /* about to wrap */
    sample_t s;
    for (int i = 0; i < 40; i++) {
        CHECK(sampler_poll(&smp));
        CHECK(sampler_pop(&smp, &s));
        CHECK_EQ(s.code, -100 + i);
    }
    CHECK_EQ(sampler_count(&smp), 0);
}

static void test_flagged_samples_are_delivered_and_counted(void)
{
    setup();
    dev.error_flag = true;
    CHECK(sampler_poll(&smp));
    sample_t s;
    CHECK(sampler_pop(&smp, &s));
    CHECK(s.status & AD7124_STATUS_ERROR);
    CHECK_EQ(smp.device_errors, 1);
}

static void test_bus_error_drops_without_numbering(void)
{
    setup();
    dev.fail_bus_after = (int)dev.log_count;
    CHECK(!sampler_on_ready(&smp));
    CHECK_EQ(smp.bus_errors, 1);
    CHECK_EQ(smp.seq, 0);
}

static void test_capture_skips_flagged_and_gives_up(void)
{
    setup();
    int32_t buf[8];
    CHECK_EQ(sampler_capture(&smp, buf, 8), 8);
    CHECK_EQ(buf[0], -100);
    CHECK_EQ(buf[7], -93);
    /* A converter that flags every sample must not hang the caller. */
    dev.error_flag = true;
    CHECK_EQ(sampler_capture(&smp, buf, 8), 0);
    CHECK(smp.device_errors >= 8);
    /* Nor must one whose RDY line never falls. */
    dev.error_flag = false;
    dev.stuck_not_ready = true;
    adc.ready_poll_limit = 10;
    CHECK_EQ(sampler_capture(&smp, buf, 8), 0);
    CHECK_EQ(adc.timeouts, 1);
}

void test_sampler(void)
{
    RUN(test_samples_arrive_in_order_and_numbered);
    RUN(test_overflow_is_counted_and_visible_in_sequence);
    RUN(test_indices_wrap_cleanly);
    RUN(test_flagged_samples_are_delivered_and_counted);
    RUN(test_bus_error_drops_without_numbering);
    RUN(test_capture_skips_flagged_and_gives_up);
}
