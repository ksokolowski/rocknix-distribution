// SPDX-License-Identifier: GPL-2.0-or-later
// a12-update-splash (B12 step 6): the initramfs update screen on KMS draws
// the logo, a status line and the progress bar (TEST_LOG test 61).
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define main update_splash_main
#include "../packages/a12-controls/sources/splash/update-splash.c"
#undef main

static uint32_t px(struct splash_frame *f, int x, int y) { return f->px[y * f->stride_px + x]; }

static int row_has_ink(struct splash_frame *f, int y0, int h)
{
	for (int y = y0; y < y0 + h; y++)
		for (int x = 0; x < f->width; x++)
			if (px(f, x, y))
				return 1;
	return 0;
}

int main(void)
{
	struct splash_frame f = { calloc(1024 * 600, 4), 1024, 600, 1024 };
	struct splash_layout l;
	splash_layout_for(f.width, f.height, &l);
	int mid = l.bar_y + l.bar_h / 2;

	/* Half done: the left half of the bar is the red gradient, the right grey. */
	update_splash_draw(&f, "/nonexistent/logo.bmp", "Updating System...", 0.5);
	assert(px(&f, l.bar_x + 2, mid) == SPLASH_BAR_FG_LEFT);
	assert(px(&f, l.bar_x + l.bar_w - 1, mid) != 0 && px(&f, l.bar_x + l.bar_w - 1, mid) != SPLASH_BAR_FG_RIGHT);
	assert((px(&f, l.bar_x + l.bar_w / 2 - 2, mid) >> 16) > (px(&f, l.bar_x + l.bar_w / 2 + 2, mid) >> 16));
	assert(row_has_ink(&f, l.text_y, l.text_h));
	/* Missing logo: black around the bar and text. */
	assert(px(&f, 10, 10) == 0 && px(&f, f.width / 2, f.height / 3) == 0);

	/* Unknown progress (spinner): text only, no bar. */
	memset(f.px, 0, 1024 * 600 * 4);
	update_splash_draw(&f, "/nonexistent/logo.bmp", "Checking disk...", -1);
	assert(px(&f, l.bar_x + 2, mid) == 0);
	assert(row_has_ink(&f, l.text_y, l.text_h));

	/* Arguments: TEXT [PERCENT]; percent clamps to 0..100, absent = -1. */
	assert(update_splash_fraction(NULL) < 0);
	assert(update_splash_fraction("37") == 0.37);
	assert(update_splash_fraction("250") == 1.0 && update_splash_fraction("-5") == 0.0);
	assert(update_splash_fraction("x") < 0);
	puts("update splash: ok");
	return 0;
}
