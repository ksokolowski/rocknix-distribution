// SPDX-License-Identifier: GPL-2.0-or-later
/* Sequential memory bandwidth and sleep precision, identical on KNULLI and ROCKNIX. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define SIZE (16u << 20)
#define ROUNDS 8

static double now(void)
{
	struct timespec t;

	if (clock_gettime(CLOCK_MONOTONIC, &t) != 0) {
		perror("clock_gettime");
		exit(1);
	}
	return t.tv_sec + t.tv_nsec / 1e9;
}

static double sleep_us(unsigned int request, int count)
{
	double start = now();
	int i;

	for (i = 0; i < count; i++)
		usleep(request);
	return (now() - start) / count * 1e6;
}

int main(void)
{
	unsigned char *a = malloc(SIZE), *b = malloc(SIZE);
	volatile unsigned long sink = 0;
	const unsigned long *word;
	double start, copy, set, read;
	size_t i;
	int r;

	if (!a || !b)
		return 1;
	memset(a, 1, SIZE);
	memset(b, 2, SIZE);
	start = now();
	for (r = 0; r < ROUNDS; r++)
		memcpy(b, a, SIZE);
	copy = now() - start;
	start = now();
	for (r = 0; r < ROUNDS; r++)
		memset(a, r, SIZE);
	set = now() - start;
	start = now();
	for (r = 0; r < ROUNDS; r++)
		for (word = (const unsigned long *)a, i = 0; i < SIZE / sizeof(*word); i++)
			sink += word[i];
	read = now() - start;
	/* copy moves each byte twice (read + write). */
	printf("{\"copy_mb_s\": %.1f, \"set_mb_s\": %.1f, \"read_mb_s\": %.1f, "
	       "\"sleep_1ms_us\": %.1f, \"sleep_16ms_us\": %.1f, \"sink\": %lu}\n",
	       2.0 * SIZE * ROUNDS / copy / 1e6, 1.0 * SIZE * ROUNDS / set / 1e6,
	       1.0 * SIZE * ROUNDS / read / 1e6, sleep_us(1000, 200), sleep_us(16000, 30),
	       (unsigned long)sink);
	free(a);
	free(b);
	return 0;
}
