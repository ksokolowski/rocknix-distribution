/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SPLASH_ATLAS_H
#define SPLASH_ATLAS_H
#include "splash-draw.h"
/* Status line from the build-time glyph table (splash-glyphs.h, gen-glyphs):
 * splash-ttf.c's pixels without FreeType. Built only with SPLASH_ATLAS. */
int splash_atlas_text(struct splash_frame *f, const struct splash_layout *l, const char *text);
#endif
