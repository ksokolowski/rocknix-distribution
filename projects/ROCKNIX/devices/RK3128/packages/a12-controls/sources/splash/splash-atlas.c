// SPDX-License-Identifier: GPL-2.0-or-later
// A12 splash status line from a build-time glyph table (gen-glyphs): the
// same pixels as splash-ttf.c without FreeType, for the initramfs (test 61).
#ifdef SPLASH_ATLAS
#include <string.h>
#include "splash-atlas.h"
#include "splash-glyphs.h"

#define TEXT_MARGIN 16

static const struct splash_glyph *glyph(unsigned char ch)
{
	return ch >= 32 && ch < 127 ? &splash_glyphs[ch - 32] : NULL;
}

static int width_of(const char *s, size_t n)
{
	int w = 0;
	for (size_t i = 0; i < n; i++) {
		const struct splash_glyph *g = glyph((unsigned char)s[i]);
		w += g ? g->advance_load : 0;
	}
	return w;
}

int splash_atlas_text(struct splash_frame *f, const struct splash_layout *l, const char *text)
{
	char line[256];
	size_t n = strlen(text);
	if (n >= sizeof(line) - 4)
		n = sizeof(line) - 4;
	memcpy(line, text, n);
	line[n] = 0;
	int max = f->width - 2 * TEXT_MARGIN;
	if (width_of(line, n) > max) {
		int dots = width_of("...", 3);
		while (n > 0 && width_of(line, n) + dots > max)
			n--;
		memcpy(line + n, "...", 4);
		n += 3;
	}
	splash_fill(f, 0, l->text_y, f->width, l->text_h, 0);
	int x = (f->width - width_of(line, n)) / 2;
	int baseline = l->text_y + (l->text_h - SPLASH_GLYPH_ASCENDER - SPLASH_GLYPH_DESCENDER) / 2 +
		       SPLASH_GLYPH_ASCENDER;
	for (size_t i = 0; i < n; i++) {
		const struct splash_glyph *g = glyph((unsigned char)line[i]);
		if (!g)
			continue;
		const uint8_t *bits = splash_glyph_px + g->offset;
		for (int row = 0; row < g->rows; row++) {
			int y = baseline - g->top + row;
			if (y < l->text_y || y >= l->text_y + l->text_h)
				continue;
			for (int col = 0; col < g->width; col++) {
				int px = x + g->left + col;
				uint32_t a = bits[row * g->width + col];
				if (a && px >= 0 && px < f->width)
					f->px[y * f->stride_px + px] = a << 16 | a << 8 | a;
			}
		}
		x += g->advance_render;
	}
	return 0;
}
#endif
