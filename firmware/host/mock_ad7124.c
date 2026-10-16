/*
 * Mocked AD7124-8 class converter. See mock_ad7124.h.
 */
#include "mock_ad7124.h"

#include <string.h>

#define ADDR_STATUS 0x00u
#define ADDR_ADC_CONTROL 0x01u
#define ADDR_DATA 0x02u
#define ADDR_ID 0x05u
#define ADDR_ERROR 0x06u
#define CTRL_DATA_STATUS (1u << 10)
#define CTRL_MODE(v) (((v) >> 2) & 0xFu)

unsigned mock_reg_size(uint8_t reg)
{
    static const uint8_t fixed[9] = {1, 2, 3, 3, 2, 1, 3, 3, 1};
    if (reg < 9)
        return fixed[reg];
    if (reg < 0x19)
        return 2;   /* CHANNEL_0 .. CHANNEL_15 */
    if (reg < 0x21)
        return 2;   /* CONFIG_0 .. CONFIG_7 */
    if (reg < 0x39)
        return 3;   /* FILTER, OFFSET, GAIN */
    return 0;
}

static bool read_only(uint8_t reg)
{
    return reg == ADDR_STATUS || reg == ADDR_DATA || reg == ADDR_ID ||
           reg == ADDR_ERROR;
}

void mock_power_on(mock_ad7124_t *m)
{
    memset(m->regs, 0, sizeof m->regs);
    m->regs[ADDR_STATUS] = 0x80u | 0x10u;          /* not ready, POR */
    m->regs[ADDR_ID] = m->id_value;
    m->regs[0x09] = 0x8001u;                       /* CHANNEL_0 enabled */
    for (unsigned c = 1; c < 16; c++)
        m->regs[0x09 + c] = 0x0001u;
    for (unsigned s = 0; s < 8; s++) {
        m->regs[0x19 + s] = 0x0860u;               /* CONFIG: bipolar */
        m->regs[0x21 + s] = 0x060180u;             /* FILTER: sinc4, FS 384 */
        m->regs[0x29 + s] = 0x800000u;             /* OFFSET */
        m->regs[0x31 + s] = 0x500000u;             /* GAIN, nominal */
    }
    m->ready = false;
}

void mock_init(mock_ad7124_t *m)
{
    memset(m, 0, sizeof *m);
    m->id_value = 0x14u;
    m->auto_ready = true;
    m->fail_bus_after = -1;
    mock_power_on(m);
}

static void log_xfer(mock_ad7124_t *m, const uint8_t *tx, size_t n)
{
    mock_xfer_t *e = &m->log[m->log_count % MOCK_LOG_DEPTH];
    e->n = n;
    memset(e->tx, 0, sizeof e->tx);
    memcpy(e->tx, tx, n < MOCK_MAX_XFER ? n : MOCK_MAX_XFER);
    m->log_count++;
}

const mock_xfer_t *mock_last(const mock_ad7124_t *m, unsigned back)
{
    if (back >= m->log_count || back >= MOCK_LOG_DEPTH)
        return NULL;
    return &m->log[(m->log_count - 1u - back) % MOCK_LOG_DEPTH];
}

static uint8_t status_byte(const mock_ad7124_t *m)
{
    uint8_t s = (uint8_t)(m->regs[ADDR_STATUS] & 0x10u);   /* POR */
    if (!m->ready)
        s |= 0x80u;
    if (m->error_flag)
        s |= 0x40u;
    return s;   /* active channel 0 */
}

static int xfer(void *ctx, const uint8_t *tx, uint8_t *rx, size_t n)
{
    mock_ad7124_t *m = ctx;
    uint8_t scratch[MOCK_MAX_XFER];
    if (rx == NULL)
        rx = scratch;
    if (n == 0 || n > MOCK_MAX_XFER)
        return -1;
    log_xfer(m, tx, n);
    if (m->fail_bus_after >= 0 && (int)m->log_count > m->fail_bus_after)
        return -1;
    memset(rx, 0xFF, n);

    /* Serial reset: at least 64 consecutive ones. */
    if (n >= 8) {
        bool ones = true;
        for (size_t i = 0; i < n; i++)
            ones = ones && tx[i] == 0xFFu;
        if (ones) {
            mock_power_on(m);
            m->resets++;
            return 0;
        }
    }

    uint8_t comms = tx[0];
    uint8_t reg = comms & 0x3Fu;
    unsigned size = mock_reg_size(reg);
    if ((comms & 0x80u) || size == 0) {
        m->protocol_errors++;
        return 0;
    }

    if (comms & 0x40u) {                            /* read */
        uint32_t v;
        unsigned extra = 0;
        if (reg == ADDR_STATUS) {
            v = status_byte(m);
        } else if (reg == ADDR_DATA) {
            v = m->regs[ADDR_DATA];
            if (m->regs[ADDR_ADC_CONTROL] & CTRL_DATA_STATUS)
                extra = 1;
        } else {
            v = m->regs[reg];
        }
        if (n != 1u + size + extra) {
            m->protocol_errors++;
            return 0;
        }
        for (unsigned i = 0; i < size; i++)
            rx[1 + i] = (uint8_t)(v >> (8u * (size - 1u - i)));
        if (extra)
            rx[1 + size] = status_byte(m);
        if (reg == ADDR_DATA) {
            m->ready = false;
            m->regs[ADDR_STATUS] &= ~0x10u;         /* POR clears on read */
        }
        return 0;
    }

    /* write */
    if (n != 1u + size || read_only(reg)) {
        m->protocol_errors++;
        return 0;
    }
    uint32_t v = 0;
    for (unsigned i = 0; i < size; i++)
        v = (v << 8) | tx[1 + i];
    if (!m->ignore_writes)
        m->regs[reg] = v;
    return 0;
}

static bool data_ready(void *ctx)
{
    mock_ad7124_t *m = ctx;
    if (m->stuck_not_ready)
        return false;
    if (!m->ready && m->auto_ready &&
        CTRL_MODE(m->regs[ADDR_ADC_CONTROL]) == 0u && m->next_code != NULL) {
        int32_t code;
        if (m->next_code(m->source_ctx, &code)) {
            if (code > 0x7FFFFF)
                code = 0x7FFFFF;
            if (code < -0x800000)
                code = -0x800000;
            m->regs[ADDR_DATA] = (uint32_t)(code + 0x800000) & 0xFFFFFFu;
            m->ready = true;
            m->conversions++;
        }
    }
    return m->ready;
}

static void delay_us(void *ctx, uint32_t us)
{
    mock_ad7124_t *m = ctx;
    m->elapsed_us += us;
}

hal_spi_t mock_hal(mock_ad7124_t *m)
{
    hal_spi_t h = {m, xfer, data_ready, delay_us};
    return h;
}
