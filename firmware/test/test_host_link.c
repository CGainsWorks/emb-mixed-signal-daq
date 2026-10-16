/*
 * Host link framing tests. The Python decoder is tested against the same
 * layout in tests/test_host_tools.py.
 */
#include <string.h>

#include "host_link.h"
#include "unit.h"

static uint8_t sink[4096];
static size_t sink_len;
static int fail_writes;

static int sink_write(void *ctx, const uint8_t *d, size_t n)
{
    (void)ctx;
    if (fail_writes)
        return -1;
    memcpy(sink + sink_len, d, n);
    sink_len += n;
    return 0;
}

static void test_crc_check_value(void)
{
    /* CRC-16/CCITT-FALSE of "123456789" is 0x29B1. */
    CHECK_EQ(hl_crc16((const uint8_t *)"123456789", 9), 0x29B1);
}

static void test_frame_layout(void)
{
    uint8_t buf[HL_FRAME_MAX];
    int32_t w[2] = {1, -2};
    size_t n = hl_encode(buf, HL_FRAME_SAMPLES, 0x1234, w, 2);
    CHECK_EQ(n, 6 + 8 + 2);
    CHECK_EQ(buf[0], 0xA5);
    CHECK_EQ(buf[1], 0x5A);
    CHECK_EQ(buf[2], 0x01);
    CHECK_EQ(buf[3], 0x34);
    CHECK_EQ(buf[4], 0x12);
    CHECK_EQ(buf[5], 2);
    CHECK_EQ(buf[6], 1);
    CHECK_EQ(buf[10], 0xFE);
    CHECK_EQ(buf[13], 0xFF);
    uint16_t crc = hl_crc16(&buf[2], n - 4);
    CHECK_EQ(buf[n - 2], crc & 0xFF);
    CHECK_EQ(buf[n - 1], crc >> 8);
    CHECK_EQ(hl_encode(buf, 1, 0, w, HL_MAX_WORDS + 1), 0);
}

static void test_sequence_advances_even_on_failure(void)
{
    host_link_t hl;
    int32_t w = 7;
    sink_len = 0;
    fail_writes = 0;
    hl_init(&hl, NULL, sink_write);
    CHECK_EQ(hl_send(&hl, HL_FRAME_RAW, &w, 1), 0);
    fail_writes = 1;
    CHECK_EQ(hl_send(&hl, HL_FRAME_RAW, &w, 1), -1);
    fail_writes = 0;
    CHECK_EQ(hl_send(&hl, HL_FRAME_RAW, &w, 1), 0);
    /* The host sees sequence 0 then 2, a visible gap. */
    CHECK_EQ(sink[3], 0);
    CHECK_EQ(sink[3 + 12], 2);
    CHECK_EQ(hl.frames_sent, 2);
    CHECK_EQ(hl.write_errors, 1);
}

void test_host_link(void)
{
    RUN(test_crc_check_value);
    RUN(test_frame_layout);
    RUN(test_sequence_advances_even_on_failure);
}
