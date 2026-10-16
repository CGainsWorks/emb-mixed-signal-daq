/*
 * Sampling engine. See sampling_engine.h.
 *
 * The ring indices run freely and are masked on use, so head - tail is the
 * fill level without a separate counter that both sides would have to
 * update. On a Cortex-M a 32-bit aligned load or store is atomic, which is
 * all the single producer, single consumer arrangement needs; a memory
 * barrier is placed where the producer publishes the new head.
 */
#include "sampling_engine.h"

#include <string.h>

#if defined(__arm__)
#define PUBLISH_BARRIER() __asm volatile("dmb" ::: "memory")
#else
#define PUBLISH_BARRIER() __asm__ volatile("" ::: "memory")
#endif

#define MASK (SAMPLER_RING_SIZE - 1u)

_Static_assert((SAMPLER_RING_SIZE & MASK) == 0, "ring size must be a power of two");

void sampler_init(sampler_t *s, adc_t *adc)
{
    memset(s, 0, sizeof *s);
    s->adc = adc;
}

uint32_t sampler_count(const sampler_t *s)
{
    return s->head - s->tail;
}

bool sampler_on_ready(sampler_t *s)
{
    adc_sample_t smp;
    adc_status_t st = adc_read_sample(s->adc, &smp);
    if (st == ADC_ERR_BUS) {
        s->bus_errors++;
        return false;
    }
    /* A sample with the device error flag is still delivered, flagged, so the
     * host sees when it happened; it is counted here as well. */
    if (st == ADC_ERR_DEVICE)
        s->device_errors++;

    uint32_t seq = s->seq++;
    s->produced++;
    if (s->head - s->tail >= SAMPLER_RING_SIZE) {
        s->overflows++;
        return false;
    }
    sample_t *slot = &s->ring[s->head & MASK];
    slot->code = smp.code;
    slot->status = smp.status;
    slot->seq = seq;
    PUBLISH_BARRIER();
    s->head++;
    return true;
}

bool sampler_poll(sampler_t *s)
{
    if (!s->adc->hal.data_ready(s->adc->hal.ctx))
        return false;
    return sampler_on_ready(s);
}

bool sampler_pop(sampler_t *s, sample_t *out)
{
    if (s->head == s->tail)
        return false;
    *out = s->ring[s->tail & MASK];
    PUBLISH_BARRIER();
    s->tail++;
    return true;
}

uint32_t sampler_capture(sampler_t *s, int32_t *codes, uint32_t n)
{
    uint32_t got = 0;
    uint32_t flagged = 0;
    while (got < n && flagged <= n) {
        adc_sample_t smp;
        if (adc_wait_ready(s->adc) != ADC_OK)
            break;
        adc_status_t st = adc_read_sample(s->adc, &smp);
        if (st == ADC_ERR_BUS) {
            s->bus_errors++;
            break;
        }
        if (st == ADC_ERR_DEVICE) {
            /* Flagged samples are discarded from a calibration capture; a
             * converter that flags everything must not hang the caller. */
            s->device_errors++;
            flagged++;
            continue;
        }
        codes[got++] = smp.code;
    }
    return got;
}
