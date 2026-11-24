// SPDX-License-Identifier: GPL-2.0-or-later
// A12 splash status line rendered with FreeType (splash polish, BACKLOG item 0).
#ifdef SPLASH_TTF
#include <stdlib.h>
#include <string.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include "splash-ttf.h"

#define TEXT_MARGIN 16

static const char *const fonts[] = {
	"/usr/config/emulationstation/resources/opensans_hebrew_condensed_regular.ttf",
	"/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
};
static FT_Library library;
static FT_Face face;
static int state;	/* 0 untried, 1 loaded, -1 unavailable */

static int load(int pixel_height)
{
	if (state)
		return state;
	state = -1;
	if (FT_Init_FreeType(&library))
		return state;
	const char *env = getenv("A12_SPLASH_FONT");
	if (env && !FT_New_Face(library, env, 0, &face))
		state = 1;
	for (size_t i = 0; state < 0 && i < sizeof(fonts) / sizeof(fonts[0]); i++)
		if (!FT_New_Face(library, fonts[i], 0, &face))
			state = 1;
	if (state > 0 && FT_Set_Pixel_Sizes(face, 0, (FT_UInt)pixel_height))
		state = -1;
	return state;
}

static int advance(unsigned char ch)
{
	if (FT_Load_Char(face, ch, FT_LOAD_DEFAULT))
		return 0;
	return (int)(face->glyph->advance.x >> 6);
}

static int width_of(const char *s, size_t n)
{
	int w = 0;
	for (size_t i = 0; i < n; i++)
		w += advance((unsigned char)s[i]);
	return w;
}

int splash_ttf_text(struct splash_frame *f, const struct splash_layout *l, const char *text)
{
	/* Glyphs about three quarters of the text row, like ES's medium font. */
	if (load(l->text_h * 3 / 4) < 0)
		return -1;
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
	int ascender = (int)(face->size->metrics.ascender >> 6);
	int descender = (int)(-face->size->metrics.descender >> 6);
	int baseline = l->text_y + (l->text_h - ascender - descender) / 2 + ascender;
	for (size_t i = 0; i < n; i++) {
		unsigned char ch = (unsigned char)line[i];
		if (FT_Load_Char(face, ch, FT_LOAD_RENDER))
			continue;
		FT_GlyphSlot g = face->glyph;
		for (unsigned int row = 0; row < g->bitmap.rows; row++) {
			int y = baseline - g->bitmap_top + (int)row;
			if (y < l->text_y || y >= l->text_y + l->text_h)
				continue;
			for (unsigned int col = 0; col < g->bitmap.width; col++) {
				int px = x + g->bitmap_left + (int)col;
				uint32_t a = g->bitmap.buffer[row * (unsigned int)g->bitmap.pitch + col];
				if (a && px >= 0 && px < f->width)
					f->px[y * f->stride_px + px] = a << 16 | a << 8 | a;
			}
		}
		x += (int)(g->advance.x >> 6);
	}
	return 0;
}
#endif
