#include "unit.h"

int unit_checks;
int unit_failures;

void test_adc_spi(void);
void test_sampler(void);
void test_calibration(void);
void test_host_link(void);
void test_daq_app(void);

int main(void)
{
    test_adc_spi();
    test_sampler();
    test_calibration();
    test_host_link();
    test_daq_app();
    printf("\n%d checks, %d failed\n", unit_checks, unit_failures);
    return unit_failures ? 1 : 0;
}
