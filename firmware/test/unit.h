/*
 * A test harness small enough to read in one go. No framework dependency,
 * so the tests build anywhere a C11 compiler does.
 */
#ifndef UNIT_H
#define UNIT_H

#include <stdio.h>

extern int unit_checks;
extern int unit_failures;

#define CHECK(cond)                                                          \
    do {                                                                     \
        unit_checks++;                                                       \
        if (!(cond)) {                                                       \
            unit_failures++;                                                 \
            fprintf(stderr, "%s:%d: CHECK(%s) failed\n", __FILE__, __LINE__, \
                    #cond);                                                  \
        }                                                                    \
    } while (0)

#define CHECK_EQ(a, b)                                                       \
    do {                                                                     \
        long long a_ = (long long)(a), b_ = (long long)(b);                  \
        unit_checks++;                                                       \
        if (a_ != b_) {                                                      \
            unit_failures++;                                                 \
            fprintf(stderr, "%s:%d: %s == %s failed: %lld != %lld\n",        \
                    __FILE__, __LINE__, #a, #b, a_, b_);                     \
        }                                                                    \
    } while (0)

#define RUN(test)                                                            \
    do {                                                                     \
        int before_ = unit_failures;                                         \
        test();                                                              \
        printf("%-48s %s\n", #test, unit_failures == before_ ? "ok" : "FAIL"); \
    } while (0)

#endif
