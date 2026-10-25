/* SPDX-License-Identifier: GPL-2.0-or-later */
/* A12 splash drawing on an in-memory XRGB8888 frame (see the boot splash spec). */
#ifndef SPLASH_DRAW_H
#define SPLASH_DRAW_H
#include <stdint.h>
#include <stdio.h>

#define SPLASH_TEXT_SCALE 2
/* ES Splash.cpp colours: inactive grey at 50 % over black, active red gradient. */
#define SPLASH_BAR_BG_LEFT  0x303030u
#define SPLASH_BAR_BG_RIGHT 0x484848u
#define SPLASH_BAR_FG_LEFT  0xDF1010u
#define SPLASH_BAR_FG_RIGHT 0x4F0000u

struct splash_frame { uint32_t *px; int width; int height; int stride_px; };
struct splash_layout { int bar_x, bar_y, bar_w, bar_h, text_y, text_h; };

void splash_layout_for(int width, int height, struct splash_layout *out);
void splash_fill(struct splash_frame *f, int x, int y, int w, int h, uint32_t rgb);
void splash_bar(struct splash_frame *f, const struct splash_layout *l, double fraction);
void splash_text(struct splash_frame *f, const struct splash_layout *l, const char *text);
/* Black out the bar and text rows, leaving only the logo (shown again
 * whenever ES releases the display, e.g. before a game starts). */
void splash_clear_progress(struct splash_frame *f, const struct splash_layout *l);
int splash_write_bmp(const struct splash_frame *f, FILE *out);
int splash_read_bmp(struct splash_frame *f, FILE *in);
#endif
