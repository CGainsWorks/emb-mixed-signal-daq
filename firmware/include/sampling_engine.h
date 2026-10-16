/*
 * Sampling engine: moves conversions from the converter to the main loop.
 *
 * On the target, sampler_on_ready() runs in the EXTI interrupt raised by the
 * falling edge of DOUT/RDY and reads one sample over SPI into a single
 * producer, single consumer ring. The main loop drains the ring with
 * sampler_pop(), calibrates and frames the samples. Nothing in the ring path
 * blocks or allocates.
 *
 * Every sample is numbered, so the host can tell a lost sample from a quiet
 * input. Overflows, device errors and bus failures are counted rather than
 * dropped silently.
 */
#ifndef SAMPLING_ENGINE_H
#define SAMPLING_ENGINE_H

#include <stdbool.h>
#include <stdint.h>

#include "adc_spi.h"

#define SAMPLER_RING_SIZE 256u   /* power of two */

typedef struct {
    int32_t code;
    uint32_t seq;
    uint8_t status;
} sample_t;

typedef struct {
    adc_t *adc;
    sample_t ring[SAMPLER_RING_SIZE];
    volatile uint32_t head;       /* written by the producer only */
    volatile uint32_t tail;       /* written by the consumer only */
    uint32_t seq;
    uint32_t produced;
    uint32_t overflows;
    uint32_t device_errors;
    uint32_t bus_errors;
} sampler_t;

void sampler_init(sampler_t *s, adc_t *adc);
/* Producer: call when DOUT/RDY falls. Returns false if the sample was lost. */
bool sampler_on_ready(sampler_t *s);
/* Producer for builds without the interrupt: checks the line, then reads. */
bool sampler_poll(sampler_t *s);
/* Consumer. */
bool sampler_pop(sampler_t *s, sample_t *out);
uint32_t sampler_count(const sampler_t *s);
/* Blocking capture of n samples straight from the converter, used by the
 * calibration routine before streaming starts. Returns samples taken. */
uint32_t sampler_capture(sampler_t *s, int32_t *codes, uint32_t n);

#endif
