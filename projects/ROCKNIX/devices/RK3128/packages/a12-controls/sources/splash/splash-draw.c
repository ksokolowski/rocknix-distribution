// SPDX-License-Identifier: GPL-2.0-or-later
// A12 splash drawing; geometry and colours follow ES es-core/src/Splash.cpp.
#include <string.h>
#include "splash-draw.h"
#include "splash-font.h"
#ifdef SPLASH_TTF
#include "splash-ttf.h"
#endif
#ifdef SPLASH_ATLAS
#include "splash-atlas.h"
#endif

#define TEXT_MARGIN 16

static int iround(double v) { return (int)(v + 0.5); }

void splash_layout_for(int width, int height, struct splash_layout *out)
{
	out->bar_w = width / 2;
	out->bar_x = (width - out->bar_w) / 2;
	out->bar_h = iround(height * 0.036);
	out->bar_y = height - iround(height * 3 * 0.036);
	out->text_y = iround(height * 0.78);
	out->text_h = 16 * SPLASH_TEXT_SCALE;
}

void splash_fill(struct splash_frame *f, int x, int y, int w, int h, uint32_t rgb)
{
	if (x < 0) { w += x; x = 0; }
	if (y < 0) { h += y; y = 0; }
	if (x + w > f->width) w = f->width - x;
	if (y + h > f->height) h = f->height - y;
	for (int j = y; j < y + h; j++)
		for (int i = x; i < x + w; i++)
			f->px[j * f->stride_px + i] = rgb;
}

static uint32_t lerp(uint32_t a, uint32_t b, int i, int n)
{
	uint32_t out = 0;
	for (int s = 0; s <= 16; s += 8) {
		int ca = (a >> s) & 0xFF, cb = (b >> s) & 0xFF;
		out |= (uint32_t)(ca + (cb - ca) * i / (n > 1 ? n - 1 : 1)) << s;
	}
	return out;
}

void splash_bar(struct splash_frame *f, const struct splash_layout *l, double fraction)
{
	if (fraction < 0) fraction = 0;
	if (fraction > 1) fraction = 1;
	int filled = (int)(l->bar_w * fraction);
	for (int i = 0; i < l->bar_w; i++) {
		uint32_t c = i < filled
			? lerp(SPLASH_BAR_FG_LEFT, SPLASH_BAR_FG_RIGHT, i, l->bar_w)
			: lerp(SPLASH_BAR_BG_LEFT, SPLASH_BAR_BG_RIGHT, i, l->bar_w);
		splash_fill(f, l->bar_x + i, l->bar_y, 1, l->bar_h, c);
	}
}

void splash_text(struct splash_frame *f, const struct splash_layout *l, const char *text)
{
#ifdef SPLASH_TTF
	if (splash_ttf_text(f, l, text) == 0)
		return;
#endif
#ifdef SPLASH_ATLAS
	if (splash_atlas_text(f, l, text) == 0)
		return;
#endif
	const int cw = 8 * SPLASH_TEXT_SCALE;
	int max = (f->width - 2 * TEXT_MARGIN) / cw;
	char line[256];
	size_t n = strlen(text);
	if ((int)n > max) {
		memcpy(line, text, (size_t)max - 3);
		memcpy(line + max - 3, "...", 4);
		n = (size_t)max;
	} else {
		memcpy(line, text, n + 1);
	}
	splash_fill(f, 0, l->text_y, f->width, l->text_h, 0);
	int x0 = (f->width - (int)n * cw) / 2;
	for (size_t c = 0; c < n; c++) {
		unsigned char ch = (unsigned char)line[c];
		if (ch < 32 || ch > 126) ch = '?';
		for (int row = 0; row < 16; row++) {
			uint8_t bits = splash_font[ch - 32][row];
			for (int bit = 0; bit < 8; bit++)
				if (bits & (0x80 >> bit))
					splash_fill(f, x0 + (int)c * cw + bit * SPLASH_TEXT_SCALE,
						    l->text_y + row * SPLASH_TEXT_SCALE,
						    SPLASH_TEXT_SCALE, SPLASH_TEXT_SCALE, 0xFFFFFF);
		}
	}
}

void splash_clear_progress(struct splash_frame *f, const struct splash_layout *l)
{
	splash_fill(f, 0, l->bar_y, f->width, l->bar_h, 0);
	splash_fill(f, 0, l->text_y, f->width, l->text_h, 0);
}

static void put16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static void put32(uint8_t *p, uint32_t v) { put16(p, v); put16(p + 2, v >> 16); }
static uint32_t get32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }

/* 24-bit bottom-up BMP, as FreeImage (ES) reads it. */
int splash_write_bmp(const struct splash_frame *f, FILE *out)
{
	int row = (f->width * 3 + 3) & ~3;
	uint8_t hdr[54] = { 'B', 'M' };
	put32(hdr + 2, 54 + row * f->height);
	put32(hdr + 10, 54);
	put32(hdr + 14, 40);
	put32(hdr + 18, f->width);
	put32(hdr + 22, f->height);
	put16(hdr + 26, 1);
	put16(hdr + 28, 24);
	put32(hdr + 34, row * f->height);
	if (fwrite(hdr, 1, 54, out) != 54)
		return -1;
	uint8_t line[3 * 4096 + 4] = { 0 };
	for (int y = f->height - 1; y >= 0; y--) {
		for (int x = 0; x < f->width; x++) {
			uint32_t p = f->px[y * f->stride_px + x];
			line[x * 3] = p; line[x * 3 + 1] = p >> 8; line[x * 3 + 2] = p >> 16;
		}
		if (fwrite(line, 1, row, out) != (size_t)row)
			return -1;
	}
	return fflush(out) ? -1 : 0;
}

int splash_read_bmp(struct splash_frame *f, FILE *in)
{
	uint8_t hdr[54], line[3 * 4096 + 4];
	if (fread(hdr, 1, 54, in) != 54 || hdr[0] != 'B' || hdr[1] != 'M')
		return -1;
	if ((int)get32(hdr + 18) != f->width || (int)get32(hdr + 22) != f->height || hdr[28] != 24)
		return -1;
	int row = (f->width * 3 + 3) & ~3;
	if (fseek(in, get32(hdr + 10), SEEK_SET))
		return -1;
	for (int y = f->height - 1; y >= 0; y--) {
		if (fread(line, 1, row, in) != (size_t)row)
			return -1;
		for (int x = 0; x < f->width; x++)
			f->px[y * f->stride_px + x] = line[x * 3] | line[x * 3 + 1] << 8 | line[x * 3 + 2] << 16;
	}
	return 0;
}
