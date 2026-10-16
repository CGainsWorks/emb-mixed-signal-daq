/*
 * Host link framing. See host_link.h.
 */
#include "host_link.h"

uint16_t hl_crc16(const uint8_t *data, size_t n)
{
    uint16_t crc = 0xFFFFu;
    while (n--) {
        crc ^= (uint16_t)(*data++ << 8);
        for (int k = 0; k < 8; k++) {
            uint32_t next = (uint32_t)crc << 1;
            if (crc & 0x8000u)
                next ^= 0x1021u;
            crc = (uint16_t)(next & 0xFFFFu);
        }
    }
    return crc;
}

size_t hl_encode(uint8_t *buf, uint8_t type, uint16_t seq,
                 const int32_t *words, size_t n)
{
    if (n > HL_MAX_WORDS)
        return 0;
    size_t i = 0;
    buf[i++] = HL_SYNC0;
    buf[i++] = HL_SYNC1;
    buf[i++] = type;
    buf[i++] = (uint8_t)(seq & 0xFFu);
    buf[i++] = (uint8_t)(seq >> 8);
    buf[i++] = (uint8_t)n;
    for (size_t w = 0; w < n; w++) {
        uint32_t v = (uint32_t)words[w];
        buf[i++] = (uint8_t)v;
        buf[i++] = (uint8_t)(v >> 8);
        buf[i++] = (uint8_t)(v >> 16);
        buf[i++] = (uint8_t)(v >> 24);
    }
    uint16_t crc = hl_crc16(&buf[2], i - 2u);
    buf[i++] = (uint8_t)(crc & 0xFFu);
    buf[i++] = (uint8_t)(crc >> 8);
    return i;
}

void hl_init(host_link_t *hl, void *ctx,
             int (*write)(void *ctx, const uint8_t *data, size_t n))
{
    hl->ctx = ctx;
    hl->write = write;
    hl->seq = 0;
    hl->frames_sent = 0;
    hl->write_errors = 0;
}

int hl_send(host_link_t *hl, uint8_t type, const int32_t *words, size_t n)
{
    uint8_t buf[HL_FRAME_MAX];
    size_t len = hl_encode(buf, type, hl->seq, words, n);
    if (len == 0)
        return -1;
    hl->seq++;
    if (hl->write(hl->ctx, buf, len) != 0) {
        hl->write_errors++;
        return -1;
    }
    hl->frames_sent++;
    return 0;
}
