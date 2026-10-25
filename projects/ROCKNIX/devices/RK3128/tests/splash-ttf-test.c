// SPDX-License-Identifier: GPL-2.0-or-later
// Host test for the A12 splash TTF status line (build with -DSPLASH_TTF).
// "ttf": A12_SPLASH_FONT points at a TrueType font; "fallback": no font loads.
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../packages/a12-controls/sources/splash/splash-draw.h"
#include "../packages/a12-controls/sources/splash/splash-ttf.h"

static uint32_t px[1024 * 600];
static struct splash_frame f = { px, 1024, 600, 1024 };
static struct splash_layout l;

struct span { int left, right, grey, outside; };

static struct span scan(void)
{
	struct span s = { 1024, -1, 0, 0 };
	for (int y = 0; y < 600; y++)
		for (int x = 0; x < 1024; x++) {
			uint32_t c = px[y * 1024 + x] & 0xFFFFFF;
			if (c == 0x123456 || !c)
				continue;
			if (y < l.text_y || y >= l.text_y + l.text_h)
				s.outside++;
			if (x < s.left) s.left = x;
			if (x > s.right) s.right = x;
			if (c != 0xFFFFFF)
				s.grey++;
		}
	return s;
}

static void clear(void)
{
	for (int i = 0; i < 1024 * 600; i++)
		px[i] = 0x123456;	/* anything drawn shows against this */
}

int main(int argc, char **argv)
{
	splash_layout_for(1024, 600, &l);
	int ttf = argc > 1 && strcmp(argv[1], "ttf") == 0;
	clear();
	assert(splash_ttf_text(&f, &l, "Stopping emustation") == (ttf ? 0 : -1));
	if (!ttf) {
		/* splash_text falls back to the 8x16 bitmap font: pure white, no grey. */
		splash_text(&f, &l, "Stopping emustation");
		struct span s = scan();
		assert(s.right > s.left && s.grey == 0 && s.outside == 0);
		puts("splash ttf fallback: ok");
		return 0;
	}
	struct span s = scan();
	assert(s.right > s.left);
	assert(s.grey > 0);			/* anti-aliased edges */
	assert(s.outside == 0);			/* stays in the text row */
	int centre = (s.left + s.right) / 2;
	assert(centre > 512 - 12 && centre < 512 + 12);
	/* The row is cleared before drawing: a shorter label leaves no trace. */
	splash_text(&f, &l, "Stopping a very long unit name that cannot possibly fit on the A12 panel in one line at all");
	s = scan();
	assert(s.left >= 16 && s.right <= 1024 - 16);
	splash_text(&f, &l, "ok");
	s = scan();
	assert(s.right - s.left < 100);
	puts("splash ttf: ok");
	return 0;
}
