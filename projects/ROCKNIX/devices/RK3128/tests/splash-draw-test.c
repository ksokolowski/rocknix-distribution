// SPDX-License-Identifier: GPL-2.0-or-later
// Host test for the A12 splash drawing code (Task 2 of the boot splash plan).
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../packages/a12-controls/sources/splash/splash-draw.h"

#define W 1024
#define H 600
static uint32_t buf[W * H];
static struct splash_frame frame = { buf, W, H, W };

static int count_nonblack(int x, int y, int w, int h)
{
	int n = 0;
	for (int j = y; j < y + h; j++)
		for (int i = x; i < x + w; i++)
			n += (buf[j * W + i] & 0xFFFFFF) != 0;
	return n;
}

static void test_layout(void)
{
	struct splash_layout l;
	splash_layout_for(W, H, &l);
	assert(l.bar_w == 512 && l.bar_x == 256);
	assert(l.bar_h == 22 && l.bar_y == 535);
	assert(l.text_y == 468 && l.text_h == 16 * SPLASH_TEXT_SCALE);
}

static void test_bar_fraction(void)
{
	struct splash_layout l;
	splash_layout_for(W, H, &l);
	memset(buf, 0, sizeof(buf));
	splash_bar(&frame, &l, 0.5);
	/* left half of the bar is red-ish, right half grey */
	uint32_t left = buf[(l.bar_y + 5) * W + l.bar_x + 10];
	uint32_t right = buf[(l.bar_y + 5) * W + l.bar_x + l.bar_w - 10];
	assert(((left >> 16) & 0xFF) > ((left >> 8) & 0xFF));
	assert(((right >> 16) & 0xFF) == ((right >> 8) & 0xFF));
	/* nothing outside the bar rectangle */
	assert(count_nonblack(0, 0, W, l.bar_y) == 0);
	assert(count_nonblack(0, l.bar_y + l.bar_h, W, H - l.bar_y - l.bar_h) == 0);
	splash_bar(&frame, &l, 2.0);  /* clamps */
	splash_bar(&frame, &l, -1.0);
}

static void test_text_truncation(void)
{
	struct splash_layout l;
	char longtext[300];
	splash_layout_for(W, H, &l);
	memset(longtext, 'M', sizeof(longtext) - 1);
	longtext[sizeof(longtext) - 1] = 0;
	memset(buf, 0, sizeof(buf));
	splash_text(&frame, &l, longtext);
	/* only the text line is touched and a margin of 16 px stays empty */
	assert(count_nonblack(0, 0, W, l.text_y) == 0);
	assert(count_nonblack(0, l.text_y + l.text_h, W, H - l.text_y - l.text_h) == 0);
	assert(count_nonblack(0, l.text_y, 16, l.text_h) == 0);
	assert(count_nonblack(W - 16, l.text_y, 16, l.text_h) == 0);
	assert(count_nonblack(16, l.text_y, W - 32, l.text_h) > 0);
}

static void test_final_text_only(void)
{
	struct splash_layout l;
	splash_layout_for(W, H, &l);
	for (int i = 0; i < W * H; i++)
		buf[i] = 0x123456;  /* stands for the logo frame */
	splash_text(&frame, &l, "It is safe to turn off your device");
	/* rows above and below the text line keep the old frame */
	assert(buf[0] == 0x123456 && buf[(l.text_y - 1) * W + 500] == 0x123456);
	assert(buf[(l.text_y + l.text_h) * W + 500] == 0x123456);
}

static void test_bmp_roundtrip(void)
{
	FILE *f = tmpfile();
	for (int i = 0; i < W * H; i++)
		buf[i] = (uint32_t)(i * 2654435761u) & 0xFFFFFF;
	assert(splash_write_bmp(&frame, f) == 0);
	uint32_t *copy = malloc(sizeof(buf));
	memcpy(copy, buf, sizeof(buf));
	memset(buf, 0, sizeof(buf));
	rewind(f);
	assert(splash_read_bmp(&frame, f) == 0);
	assert(memcmp(copy, buf, sizeof(buf)) == 0);
	struct splash_frame small = { buf, 640, 480, 640 };
	rewind(f);
	assert(splash_read_bmp(&small, f) != 0);  /* size mismatch is rejected */
	free(copy);
	fclose(f);
}


static void test_clear_progress_keeps_logo(void)
{
	struct splash_layout l;
	splash_layout_for(W, H, &l);
	for (int i = 0; i < W * H; i++)
		buf[i] = 0x00FF5555;  /* stands for the logo frame */
	splash_bar(&frame, &l, 0.6);
	splash_text(&frame, &l, "Starting NetworkManager");
	splash_clear_progress(&frame, &l);
	/* bar and text rows are black, the rest of the frame is untouched */
	assert(count_nonblack(0, l.bar_y, W, l.bar_h) == 0);
	assert(count_nonblack(0, l.text_y, W, l.text_h) == 0);
	assert(buf[0] == 0x00FF5555 && buf[300 * W + 512] == 0x00FF5555);
	assert(buf[(l.text_y - 1) * W + 10] == 0x00FF5555);
}

int main(void)
{
	test_layout();
	test_bar_fraction();
	test_text_truncation();
	test_final_text_only();
	test_bmp_roundtrip();
	test_clear_progress_keeps_logo();
	puts("splash draw: ok");
	return 0;
}
