// SPDX-License-Identifier: GPL-2.0-or-later
// a12-update-splash: the initramfs status screen on KMS (B12 step 6).
// Without fbdev the initramfs console is invisible, so an update showed
// nothing for minutes (TEST_LOG test 61). The busybox progress meters call
//   a12-update-splash TEXT [PERCENT]
// which draws the logo, TEXT and, with PERCENT, the progress bar, then
// exits leaving the frame on screen. With fbdev the console shows the text
// and this does nothing (exit 2, so the initramfs logo falls back to
// rocknix-splash). No systemd or FreeType: it lives in the initramfs.
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include "splash-draw.h"
#include "splash-fb.h"
#include "splash-kms.h"

#define UPDATE_SPLASH_LOGO "/usr/share/a12-splash/logo.bmp"

/* PERCENT as a fraction of 1, clamped; -1 for no or an unreadable value. */
double update_splash_fraction(const char *arg)
{
	char *end;
	long v;

	if (!arg || !*arg)
		return -1;
	v = strtol(arg, &end, 10);
	if (*end)
		return -1;
	if (v < 0)
		v = 0;
	if (v > 100)
		v = 100;
	return v / 100.0;
}

/* The whole frame: logo (black if missing), status line, and the bar when
 * the progress is known. */
void update_splash_draw(struct splash_frame *f, const char *logo, const char *text, double fraction)
{
	struct splash_layout l;
	FILE *in = fopen(logo, "rb");
	int ok = in && splash_read_bmp(f, in) == 0;

	if (in)
		fclose(in);
	if (!ok)
		splash_fill(f, 0, 0, f->width, f->height, 0);
	splash_layout_for(f->width, f->height, &l);
	splash_clear_progress(f, &l);
	if (fraction >= 0)
		splash_bar(f, &l, fraction);
	splash_text(f, &l, text);
}

int main(int argc, char **argv)
{
	struct splash_kms kms;
	struct splash_frame f;

	if (access("/dev/fb0", F_OK) == 0)
		return 2;
	/* Draw before showing: each call replaces the previous call's frame,
	 * and showing the cleared buffer first flashed black (test 61). */
	if (splash_kms_prepare(&kms, &f, "/dev/dri/card0"))
		return 1;
	if (!splash_fb_supported(f.width, f.height, 32, f.stride_px * 4)) {
		splash_kms_release(&kms);
		return 1;
	}
	update_splash_draw(&f, UPDATE_SPLASH_LOGO, argc > 1 ? argv[1] : "",
			   update_splash_fraction(argc > 2 ? argv[2] : NULL));
	if (splash_kms_show(&kms))
		return 1;
	splash_kms_release(&kms);
	return 0;
}
