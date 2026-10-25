/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SPLASH_TTF_H
#define SPLASH_TTF_H
#include "splash-draw.h"
/* Anti-aliased status line from a TrueType font (A12_SPLASH_FONT, ES's font,
 * Liberation Sans). Returns 0 when drawn, -1 when no font loads; the caller
 * then uses the bitmap font. Built only with SPLASH_TTF (FreeType). */
int splash_ttf_text(struct splash_frame *f, const struct splash_layout *l, const char *text);
#endif
