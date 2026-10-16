/*
 * Calibration tests. The vectors come from the Python reference
 * implementation run on the simulated board (scripts/run_all.py writes
 * fixtures/cal_vectors.h), so these check that C and Python agree to the
 * last bit on real looking data, not only on hand picked numbers.
 */
#include "calibration.h"
#include "fixtures/cal_vectors.h"
#include "unit.h"

static void test_round_div_is_symmetric(void)
{
    CHECK_EQ(cal_round_div(5, 2), 3);
    CHECK_EQ(cal_round_div(-5, 2), -3);
    CHECK_EQ(cal_round_div(4, 3), 1);
    CHECK_EQ(cal_round_div(-4, 3), -1);
    CHECK_EQ(cal_round_div(0, 7), 0);
    CHECK_EQ(cal_round_div(INT64_C(1) << 62, 3), INT64_C(1537228672809129301));
}

static void test_vectors_from_python(void)
{
    for (unsigned v = 0; v < CAL_VECTOR_COUNT; v++) {
        const cal_vector_t *cv = &cal_vectors[v];
        cal_accumulator_t acc;
        int64_t zero_q8 = 0, ref_q8 = 0;

        cal_acc_reset(&acc);
        for (unsigned i = 0; i < CAL_AVG; i++)
            cal_acc_add(&acc, cv->zero_codes[i]);
        CHECK_EQ(cal_acc_mean_q8(&acc, &zero_q8), CAL_OK);
        cal_acc_reset(&acc);
        for (unsigned i = 0; i < CAL_AVG; i++)
            cal_acc_add(&acc, cv->ref_codes[i]);
        CHECK_EQ(cal_acc_mean_q8(&acc, &ref_q8), CAL_OK);

        cal_coeffs_t c;
        CHECK_EQ(cal_compute(zero_q8, ref_q8, cv->vcal_nv, cv->full_scale_nv, &c), CAL_OK);
        CHECK_EQ(c.offset_q8, cv->offset_q8);
        CHECK_EQ(c.gain_q29, cv->gain_q29);
        for (unsigned i = 0; i < CAL_SPOT_COUNT; i++)
            CHECK_EQ(cal_apply(cv->spot_code[i], &c), cv->spot_out[i]);
    }
}

static void test_identity_is_a_shift(void)
{
    cal_coeffs_t c;
    cal_identity(&c);
    CHECK_EQ(cal_apply(1, &c), 256);
    CHECK_EQ(cal_apply(-1, &c), -256);
    CHECK_EQ(cal_apply(0x7FFFFF, &c), 0x7FFFFF00);
    CHECK_EQ(cal_apply(-0x800000, &c), INT32_MIN);
}

static void test_output_saturates(void)
{
    cal_coeffs_t c = {-(INT64_C(1) << 30), INT64_C(1) << 29};
    CHECK_EQ(cal_apply(0x7FFFFF, &c), INT32_MAX);
    c.offset_q8 = INT64_C(1) << 30;
    CHECK_EQ(cal_apply(-0x800000, &c), INT32_MIN);
}

static void test_implausible_span_is_refused(void)
{
    cal_coeffs_t c;
    const int64_t fs = 2500000000LL;
    const int64_t vcal = 2250000000LL;
    const int64_t expect = INT64_C(1932735283);   /* 0.9 * 2^31 */
    CHECK_EQ(cal_compute(0, expect, vcal, fs, &c), CAL_OK);
    CHECK_EQ(cal_compute(0, 0, vcal, fs, &c), CAL_ERR_SPAN);
    CHECK_EQ(cal_compute(0, -expect, vcal, fs, &c), CAL_ERR_SPAN);
    CHECK_EQ(cal_compute(0, expect / 2, vcal, fs, &c), CAL_ERR_SPAN);
    CHECK_EQ(cal_compute(0, expect * 2, vcal, fs, &c), CAL_ERR_SPAN);
    CHECK_EQ(cal_compute(0, expect, 0, fs, &c), CAL_ERR_ARG);
    CHECK_EQ(cal_compute(0, expect, fs + 1, fs, &c), CAL_ERR_ARG);
}

static void test_empty_accumulator_is_an_error(void)
{
    cal_accumulator_t acc;
    int64_t m;
    cal_acc_reset(&acc);
    CHECK_EQ(cal_acc_mean_q8(&acc, &m), CAL_ERR_ARG);
}

static void test_record_round_trip_and_corruption(void)
{
    cal_coeffs_t c = {-123456, 536900000}, back;
    cal_record_t r;
    cal_record_pack(&r, 3, &c);
    CHECK_EQ(cal_record_unpack(&r, &back), CAL_OK);
    CHECK_EQ(back.offset_q8, c.offset_q8);
    CHECK_EQ(back.gain_q29, c.gain_q29);
    r.gain_q29 ^= 1;
    CHECK_EQ(cal_record_unpack(&r, &back), CAL_ERR_CRC);
    /* CRC-32 check value. */
    CHECK_EQ(cal_crc32("123456789", 9), 0xCBF43926u);
}

void test_calibration(void)
{
    RUN(test_round_div_is_symmetric);
    RUN(test_vectors_from_python);
    RUN(test_identity_is_a_shift);
    RUN(test_output_saturates);
    RUN(test_implausible_span_is_refused);
    RUN(test_empty_accumulator_is_an_error);
    RUN(test_record_round_trip_and_corruption);
}
