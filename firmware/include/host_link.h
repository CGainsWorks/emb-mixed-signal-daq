/*
 * Framing for the link to the host capture tool (UART or USB CDC).
 *
 *   sync 0xA5 0x5A | type | seq (u16 LE) | n | n x int32 LE | CRC-16 LE
 *
 * The CRC is CRC-16/CCITT-FALSE over type, seq, n and the payload. The host
 * decoder is host-tools/daqhost/framing.py.
 */
#ifndef HOST_LINK_H
#define HOST_LINK_H

#include <stddef.h>
#include <stdint.h>

#define HL_SYNC0 0xA5u
#define HL_SYNC1 0x5Au
#define HL_MAX_WORDS 64u
#define HL_FRAME_MAX (6u + 4u * HL_MAX_WORDS + 2u)

enum {
    HL_FRAME_SAMPLES = 0x01,   /* calibrated, Q31 of full scale */
    HL_FRAME_RAW = 0x02,       /* raw signed codes */
    HL_FRAME_COEFFS = 0x03,    /* offset_q8, gain_q29 (low, high words), gain index */
    HL_FRAME_STATUS = 0x04     /* produced, overflows, device errors, bus errors, timeouts */
};

typedef struct {
    void *ctx;
    int (*write)(void *ctx, const uint8_t *data, size_t n);
    uint16_t seq;
    uint32_t frames_sent;
    uint32_t write_errors;
} host_link_t;

uint16_t hl_crc16(const uint8_t *data, size_t n);
/* Encode one frame into buf (at least HL_FRAME_MAX bytes); returns its length
 * or 0 if there are too many words. */
size_t hl_encode(uint8_t *buf, uint8_t type, uint16_t seq,
                 const int32_t *words, size_t n);
void hl_init(host_link_t *hl, void *ctx,
             int (*write)(void *ctx, const uint8_t *data, size_t n));
int hl_send(host_link_t *hl, uint8_t type, const int32_t *words, size_t n);

#endif
