// SPDX-License-Identifier: GPL-2.0-or-later
// a12-splash: boot progress on fbdev, shutdown and final screens (A12 boot splash spec).
#include <fcntl.h>
#include <linux/fb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include "splash-draw.h"
#include "splash-fb.h"
#include "splash-kms.h"
#include "splash-sd.h"

#define DIR "/storage/.cache/a12-splash"
#define LOGO DIR "/logo.bmp"
#define STAMP DIR "/stamp"
#define SECONDS DIR "/boot-seconds"
/* userconfig-setup creates it at the end of a card's first boot. */
#define CONFIGURED "/storage/.configured"

static void build_id(char *out, size_t n)
{
	FILE *f = fopen("/etc/os-release", "r");
	out[0] = 0;
	while (f && fgets(out, (int)n, f))
		if (strncmp(out, "BUILD_ID=", 9) == 0)
			break;
	if (f)
		fclose(f);
	if (strncmp(out, "BUILD_ID=", 9) != 0)
		out[0] = 0;
	out[strcspn(out, "\n")] = 0;
}

/* Returns 1 on the first boot of a new build (or a fresh install). */
static int capture_logo(const struct splash_frame *f)
{
	char id[256];
	build_id(id, sizeof(id));
	if (!id[0] || !splash_logo_needs_capture(STAMP, id))
		return 0;
	mkdir(DIR, 0755);
	FILE *out = fopen(LOGO ".new", "wb");
	if (!out)
		return 1;
	/* Logo data, then its name, then the stamp: a power cut leaves either
	 * the old logo or the complete new one, and no stamp for a short one. */
	int ok = splash_write_bmp(f, out) == 0;
	ok &= splash_close_synced(out) == 0;
	if (ok && rename(LOGO ".new", LOGO) == 0 && splash_sync_dir(LOGO) == 0) {
		FILE *s = fopen(STAMP, "w");
		if (s) {
			fprintf(s, "%s\n", id);
			splash_close_synced(s);
		}
	}
	return 1;
}

/* Logo for a surface that starts black (KMS): the image's logo if shipped,
 * else the one captured from fbdev by an earlier boot. */
static void draw_logo(struct splash_frame *f)
{
	/* A12_SPLASH_LOGO: the initramfs passes the system image's copy. */
	const char *logos[] = { getenv("A12_SPLASH_LOGO"), "/usr/share/a12-splash/logo.bmp", LOGO };
	for (size_t i = 0; i < sizeof(logos) / sizeof(logos[0]); i++) {
		if (!logos[i])
			continue;
		FILE *in = fopen(logos[i], "rb");
		int ok = in && splash_read_bmp(f, in) == 0;
		if (in)
			fclose(in);
		if (ok)
			return;
	}
	splash_fill(f, 0, 0, f->width, f->height, 0);
}

static int run(const char *mode, struct splash_frame *f, int kms)
{
	struct splash_layout l;
	splash_layout_for(f->width, f->height, &l);

	if (strcmp(mode, "--logo") == 0) {
		/* Initramfs (a12_kms_splash): the logo alone until a12-splash starts. */
		draw_logo(f);
		return 0;
	}
	if (strcmp(mode, "--final") == 0) {
		/* fbdev still shows the shutdown frame: only replace the text line.
		 * /storage may be unmounted, so KMS gets the shipped logo if any. */
		if (kms)
			draw_logo(f);
		splash_text(f, &l, "It is safe to turn off your device");
		return 0;
	}
	if (strcmp(mode, "--shutdown") == 0 || strcmp(mode, "--stopping") == 0) {
		draw_logo(f);
		splash_fill(f, l.bar_x, l.bar_y, l.bar_w, l.bar_h, 0);
		splash_text(f, &l, "Shutting down...");
		/* --stopping (a12-splash-stopping.service, started with the
		 * shutdown transaction) then follows the stop jobs. */
		if (strcmp(mode, "--stopping") == 0)
			return splash_sd_stopping(f, &l);
		return 0;
	}
	/* The first boot of a build is slow (update, hwdb rebuild): pace it by
	 * the previous boot but do not let it pace the next one. On KMS the
	 * frame is not rocknix-splash's, so draw the logo and keep the stamp. */
	int new_build = 0;
	if (kms)
		draw_logo(f);
	else
		new_build = capture_logo(f);
	return splash_sd_run(f, &l, SECONDS, !new_build, access(CONFIGURED, F_OK) != 0);
}

int main(int argc, char **argv)
{
	const char *mode = argc > 1 ? argv[1] : "boot";
	const char *force = getenv("A12_SPLASH_FORCE_KMS");
	/* --logo runs from the initramfs, which falls back to rocknix-splash on
	 * failure; the other modes quietly do nothing without a usable display. */
	int nothing = strcmp(mode, "--logo") == 0 ? 1 : 0;
	struct fb_var_screeninfo v;
	struct fb_fix_screeninfo fx;

	/* fbdev, as verified on hardware, unless forced to KMS (environment or
	 * the a12_kms_splash kernel argument) or absent (B12). */
	int kms_only = (force && strcmp(force, "1") == 0) || splash_cmdline_has("/proc/cmdline", "a12_kms_splash");
	int fd = kms_only ? -1 : open("/dev/fb0", O_RDWR);
	int blank = strcmp(mode, "--blank") == 0;
	if (blank && fd >= 0)
		return ioctl(fd, FBIOBLANK, FB_BLANK_POWERDOWN) ? 1 : 0;
	if (fd >= 0 && !ioctl(fd, FBIOGET_VSCREENINFO, &v) && !ioctl(fd, FBIOGET_FSCREENINFO, &fx) &&
	    splash_fb_supported(v.xres, v.yres, v.bits_per_pixel, fx.line_length)) {
		uint32_t *px = mmap(NULL, fx.line_length * v.yres, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
		if (px == MAP_FAILED)
			return nothing;
		struct splash_frame f = { px, (int)v.xres, (int)v.yres, (int)(fx.line_length / 4) };
		return run(mode, &f, 0);
	}
	if (fd >= 0)
		return nothing;	/* fbdev present but another mode (HDMI, RGB565): as before */

	struct splash_kms kms;
	struct splash_frame f;
	if (splash_kms_open(&kms, &f, "/dev/dri/card0"))
		return nothing || blank;
	if (blank) {
		/* Empty battery or overheating at power-off (shutdown hook). */
		int r = splash_kms_disable(&kms) ? 1 : 0;
		splash_kms_release(&kms);
		return r;
	}
	int r = nothing;
	if (splash_fb_supported(f.width, f.height, 32, f.stride_px * 4))
		r = run(mode, &f, 1);
	splash_kms_release(&kms);
	return r;
}
