/*
 * Two point (zero and reference) system calibration in integer arithmetic.
 *
 * The reference implementation is host-tools/daqhost/calibration.py; the
 * unit tests check this file against vectors that module generates and the
 * firmware in the loop run checks every calibrated sample bit for bit.
 *
 *   offset_q8   mean zero input code, Q8 (1/256 code)
 *   gain_q29    multiplier, about 2^29 on a perfect channel
 *   output      signed Q31 fraction of the nominal full scale Vref / G
 */
#ifndef CALIBRATION_H
#define CALIBRATION_H

#include <stddef.h>
#include <stdint.h>

#define CAL_Q_OFFSET 8
#define CAL_Q_GAIN 29
#define CAL_Q_OUT 31
#define CAL_MAGIC 0x43414C31u   /* "CAL1" */

typedef enum {
    CAL_OK = 0,
    CAL_ERR_ARG = -1,
    CAL_ERR_SPAN = -2,
    CAL_ERR_CRC = -3
} cal_status_t;

typedef struct {
    int64_t offset_q8;
    int64_t gain_q29;
} cal_coeffs_t;

/* What goes to non-volatile storage, one per gain setting. */
typedef struct {
    uint32_t magic;
    uint32_t gain_index;
    int64_t offset_q8;
    int64_t gain_q29;
    uint32_t crc32;
} cal_record_t;

/* Running mean of codes in Q8, so calibration never stores raw samples. */
typedef struct {
    int64_t sum;
    uint32_t count;
} cal_accumulator_t;

int64_t cal_round_div(int64_t a, int64_t b);
void cal_acc_reset(cal_accumulator_t *acc);
void cal_acc_add(cal_accumulator_t *acc, int32_t code);
cal_status_t cal_acc_mean_q8(const cal_accumulator_t *acc, int64_t *mean_q8);

cal_status_t cal_compute(int64_t zero_q8, int64_t ref_q8, int64_t vcal_nv,
                         int64_t full_scale_nv, cal_coeffs_t *out);
int32_t cal_apply(int32_t code, const cal_coeffs_t *c);
void cal_identity(cal_coeffs_t *c);

uint32_t cal_crc32(const void *data, size_t n);
void cal_record_pack(cal_record_t *r, uint32_t gain_index, const cal_coeffs_t *c);
cal_status_t cal_record_unpack(const cal_record_t *r, cal_coeffs_t *c);

#endif
