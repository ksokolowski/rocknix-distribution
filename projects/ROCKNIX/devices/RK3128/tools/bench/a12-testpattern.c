// SPDX-License-Identifier: GPL-2.0-or-later
/* Display check pattern for the A12 panel, identical on KNULLI and ROCKNIX.
 * Top third: 8 colour bars. Middle: 0-255 grey ramp (banding, clipped
 * black/white). Bottom: 1-pixel checkerboard (sampling-edge errors shimmer).
 * Usage: a12-testpattern            draw on /dev/fb0 (stop the frontend first)
 *        a12-testpattern --raw W H FILE   write XRGB8888 for host tests
 */
#include <fcntl.h>
#include <linux/fb.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

struct layout {
	unsigned int red, green, blue;	/* bit offsets of 8-bit channels */
};

static uint32_t pack(const struct layout *l, unsigned int r, unsigned int g, unsigned int b)
{
	return r << l->red | g << l->green | b << l->blue;
}

static void draw(uint8_t *base, unsigned int width, unsigned int height,
		 unsigned int stride, const struct layout *l)
{
	static const uint32_t bars[8] = {
		0xffffff, 0xffff00, 0x00ffff, 0x00ff00, 0xff00ff, 0xff0000, 0x0000ff, 0x000000
	};
	unsigned int x, y, r, g, b, v;

	for (y = 0; y < height; y++) {
		uint32_t *row = (uint32_t *)(base + (size_t)y * stride);

		for (x = 0; x < width; x++) {
			if (y < height / 3) {
				uint32_t c = bars[x * 8 / width];

				r = c >> 16 & 0xff;
				g = c >> 8 & 0xff;
				b = c & 0xff;
			} else if (y < height * 2 / 3) {
				v = width > 1 ? x * 255 / (width - 1) : 0;
				r = g = b = v;
			} else {
				r = g = b = (x + y) & 1 ? 255 : 0;
			}
			row[x] = pack(l, r, g, b);
		}
	}
}

int main(int argc, char **argv)
{
	struct fb_var_screeninfo var;
	struct fb_fix_screeninfo fix;
	struct layout l = { 16, 8, 0 };
	uint8_t *base;
	int fd;

	if (argc == 5 && !strcmp(argv[1], "--raw")) {
		unsigned int width = atoi(argv[2]), height = atoi(argv[3]);
		size_t size = (size_t)width * height * 4;
		FILE *out;

		base = malloc(size);
		if (!base || !width || !height)
			return 2;
		draw(base, width, height, width * 4, &l);
		out = fopen(argv[4], "wb");
		if (!out || fwrite(base, 1, size, out) != size)
			return perror(argv[4]), 1;
		fclose(out);
		free(base);
		return 0;
	}
	if (argc != 1) {
		fprintf(stderr, "usage: %s [--raw W H FILE]\n", argv[0]);
		return 2;
	}
	fd = open("/dev/fb0", O_RDWR);
	if (fd < 0)
		return perror("/dev/fb0"), 1;
	if (ioctl(fd, FBIOGET_VSCREENINFO, &var) || ioctl(fd, FBIOGET_FSCREENINFO, &fix))
		return perror("fb ioctl"), 1;
	if (var.bits_per_pixel != 32) {
		fprintf(stderr, "unsupported %u bpp\n", var.bits_per_pixel);
		return 1;
	}
	l.red = var.red.offset;
	l.green = var.green.offset;
	l.blue = var.blue.offset;
	base = mmap(NULL, fix.smem_len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if (base == MAP_FAILED)
		return perror("mmap"), 1;
	draw(base + (size_t)var.yoffset * fix.line_length, var.xres, var.yres, fix.line_length, &l);
	printf("%ux%u %u bpp, offsets r%u g%u b%u, line %u\n", var.xres, var.yres,
	       var.bits_per_pixel, l.red, l.green, l.blue, fix.line_length);
	munmap(base, fix.smem_len);
	close(fd);
	return 0;
}
