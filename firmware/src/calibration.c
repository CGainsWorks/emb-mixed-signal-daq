/*
 * Two point calibration. See calibration.h.
 *
 * Range check on the arithmetic: a code times 256 is below 2^31 in
 * magnitude, minus an offset of similar size gives below 2^32; a gain
 * below 2^30 (a correction under 2x, enforced by the span check) keeps the
 * product below 2^62, inside int64_t.
 */
#include "calibration.h"

#include <string.h>

int64_t cal_round_div(int64_t a, int64_t b)
{
    /* Round half away from zero, b > 0. C division truncates, so the sign
     * is handled explicitly rather than relying on it. */
    if (a >= 0)
        return (a + b / 2) / b;
    return -((-a + b / 2) / b);
}

void cal_acc_reset(cal_accumulator_t *acc)
{
    acc->sum = 0;
    acc->count = 0;
}

void cal_acc_add(cal_accumulator_t *acc, int32_t code)
{
    acc->sum += code;
    acc->count++;
}

cal_status_t cal_acc_mean_q8(const cal_accumulator_t *acc, int64_t *mean_q8)
{
    if (acc->count == 0)
        return CAL_ERR_ARG;
    *mean_q8 = cal_round_div(acc->sum * (1 << CAL_Q_OFFSET), (int64_t)acc->count);
    return CAL_OK;
}

cal_status_t cal_compute(int64_t zero_q8, int64_t ref_q8, int64_t vcal_nv,
                         int64_t full_scale_nv, cal_coeffs_t *out)
{
    if (out == NULL || vcal_nv <= 0 || full_scale_nv <= 0 ||
        vcal_nv > full_scale_nv)
        return CAL_ERR_ARG;
    int64_t span = ref_q8 - zero_q8;
    int64_t vcal_q31 = cal_round_div(vcal_nv * ((int64_t)1 << CAL_Q_OUT),
                                     full_scale_nv);
    /* On a perfect channel the Q8 span equals vcal_q31. Outside half to twice
     * that, the input, the gain or the channel is wrong. */
    if (span <= vcal_q31 / 2 || span >= vcal_q31 * 2)
        return CAL_ERR_SPAN;
    out->offset_q8 = zero_q8;
    out->gain_q29 = cal_round_div(vcal_q31 * ((int64_t)1 << CAL_Q_GAIN), span);
    return CAL_OK;
}

int32_t cal_apply(int32_t code, const cal_coeffs_t *c)
{
    int64_t x = (int64_t)code * (1 << CAL_Q_OFFSET) - c->offset_q8;
    int64_t y = cal_round_div(x * c->gain_q29, (int64_t)1 << CAL_Q_GAIN);
    if (y > INT32_MAX)
        return INT32_MAX;
    if (y < INT32_MIN)
        return INT32_MIN;
    return (int32_t)y;
}

void cal_identity(cal_coeffs_t *c)
{
    c->offset_q8 = 0;
    c->gain_q29 = (int64_t)1 << CAL_Q_GAIN;
}

uint32_t cal_crc32(const void *data, size_t n)
{
    /* CRC-32 (IEEE 802.3), bitwise: small and only run at boot. */
    const uint8_t *p = data;
    uint32_t crc = 0xFFFFFFFFu;
    while (n--) {
        crc ^= *p++;
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

void cal_record_pack(cal_record_t *r, uint32_t gain_index, const cal_coeffs_t *c)
{
    memset(r, 0, sizeof *r);
    r->magic = CAL_MAGIC;
    r->gain_index = gain_index;
    r->offset_q8 = c->offset_q8;
    r->gain_q29 = c->gain_q29;
    r->crc32 = cal_crc32(r, offsetof(cal_record_t, crc32));
}

cal_status_t cal_record_unpack(const cal_record_t *r, cal_coeffs_t *c)
{
    if (r->magic != CAL_MAGIC ||
        r->crc32 != cal_crc32(r, offsetof(cal_record_t, crc32)))
        return CAL_ERR_CRC;
    c->offset_q8 = r->offset_q8;
    c->gain_q29 = r->gain_q29;
    return CAL_OK;
}
