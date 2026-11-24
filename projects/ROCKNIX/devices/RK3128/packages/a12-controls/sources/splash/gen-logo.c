// SPDX-License-Identifier: GPL-2.0-or-later
// Build-host tool: render the logo rocknix-splash draws into a 1024x600 BMP
// for a12-splash's KMS path (B12 step 3). Linked with rocknix-splash's own
// main.c (main renamed) and renderer; its framebuffer, device checks and
// rotation lookup are replaced with --wrap.
#include <stdio.h>
#include <stdlib.h>
#include "fbsplash.h"
#include "splash-draw.h"

#define WIDTH 1024
#define HEIGHT 600

int rocknix_splash_main(void);

static const char *out_path;
static int written;

Framebuffer *__wrap_fb_init(const char *device)
{
	(void)device;
	Framebuffer *fb = calloc(1, sizeof(*fb));
	if (!fb)
		return NULL;
	fb->fd = -1;
	fb->vinfo.xres = fb->vinfo.xres_virtual = WIDTH;
	fb->vinfo.yres = fb->vinfo.yres_virtual = HEIGHT;
	fb->vinfo.bits_per_pixel = 32;
	fb->finfo.line_length = WIDTH * 4;
	fb->screensize = (size_t)WIDTH * 4 * HEIGHT;
	fb->buffer = calloc(1, fb->screensize);
	if (!fb->buffer) {
		free(fb);
		return NULL;
	}
	return fb;
}

void __wrap_fb_flush(Framebuffer *fb)
{
	struct splash_frame f = { (uint32_t *)(void *)fb->buffer, WIDTH, HEIGHT, WIDTH };
	FILE *out = fopen(out_path, "wb");
	if (out && splash_write_bmp(&f, out) == 0)
		written = 1;
	if (out && fclose(out))
		written = 0;
}

void __wrap_fb_cleanup(Framebuffer *fb)
{
	free(fb->buffer);
	free(fb);
}

int __wrap_access(const char *path, int mode) { (void)path; (void)mode; return 0; }
int __wrap_get_display_rotation(void) { return 0; }	/* no rotation in the A12 DT */

int main(int argc, char **argv)
{
	if (argc != 2) {
		fprintf(stderr, "usage: %s logo.bmp\n", argv[0]);
		return 2;
	}
	out_path = argv[1];
	return rocknix_splash_main() != 0 || !written;
}
