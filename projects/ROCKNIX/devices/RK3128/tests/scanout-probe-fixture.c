// SPDX-License-Identifier: GPL-2.0-or-later
/* Execute the real probe's property routing/restoration against DRM doubles. */
#define main scanout_probe_main
#include "../tools/bench/a12-scanout-probe.c"
#undef main
#include <assert.h>

static uint64_t written[MAX_PLANES][ARRAY_SIZE(property_names)];
static unsigned int additions, commits, frees, reject_addition;
static uint32_t committed_flags;

drmModeAtomicReq *__wrap_drmModeAtomicAlloc(void)
{
	return (drmModeAtomicReq *)&written;
}

int __wrap_drmModeAtomicAddProperty(drmModeAtomicReq *request,
				  uint32_t object, uint32_t property, uint64_t value)
{
	unsigned int plane = object - 10, index = property - 100;
	assert(request == (drmModeAtomicReq *)&written);
	assert(plane < 2 && index < ARRAY_SIZE(property_names));
	additions++;
	if (reject_addition && additions == reject_addition)
		return -1;
	written[plane][index] = value;
	return additions;
}

int __wrap_drmModeAtomicCommit(int fd, const drmModeAtomicReq *request,
			     uint32_t flags, void *data)
{
	assert(fd == 123 && request == (drmModeAtomicReq *)&written && !data);
	commits++;
	committed_flags = flags;
	return 0;
}

void __wrap_drmModeAtomicFree(drmModeAtomicReq *request)
{
	assert(request == (drmModeAtomicReq *)&written);
	frees++;
}

int main(void)
{
	struct display d = { .fd = 123, .crtc = 39, .nplanes = 2 };
	unsigned int plane, i;
	assert(!self_test());
	{
		struct buffer b = { .pitch = WIDTH * 4 + 64 };
		b.size = (uint64_t)b.pitch * HEIGHT;
		b.map = malloc(b.size);
		assert(b.map);
		fill_buffer(&b, DRM_FORMAT_XRGB8888, 0);
		assert(!verify_pixels(&b, DRM_FORMAT_XRGB8888, 0));
		/* An unchanged hash cannot establish that initial pixels were correct. */
		((uint32_t *)b.map)[0] = 0;
		b.hash = hash_buffer(&b);
		assert(verify_pixels(&b, DRM_FORMAT_XRGB8888, 0) < 0);
		free(b.map);
	}
	/* systemd and the wrapper can both signal during shutdown. */
	assert(!install_stop_handlers());
	assert(!raise(SIGTERM) && stopped);
	stopped = 0;
	assert(!raise(SIGTERM) && stopped);
	for (plane = 0; plane < d.nplanes; plane++) {
		d.planes[plane].id = 10 + plane;
		for (i = 0; i < ARRAY_SIZE(property_names); i++) {
			d.planes[plane].properties[i] = 100 + i;
			d.planes[plane].original[i] = 1000 + 100 * plane + i;
		}
	}
	for (plane = 0; plane < d.nplanes; plane++) {
		d.selected = plane;
		assert(!route(&d, 77, false, DRM_MODE_ATOMIC_TEST_ONLY));
		assert(committed_flags == DRM_MODE_ATOMIC_TEST_ONLY);
		assert(written[plane][0] == 77 && written[plane][1] == 39);
		assert(written[plane][2] == 0 && written[plane][3] == 0);
		assert(written[plane][4] == WIDTH && written[plane][5] == HEIGHT);
		assert(written[plane][6] == 0 && written[plane][7] == 0);
		assert(written[plane][8] == WIDTH << 16 && written[plane][9] == HEIGHT << 16);
		for (i = 0; i < ARRAY_SIZE(property_names); i++)
			assert(written[plane ^ 1][i] == 0);
	}
	assert(!route(&d, 0, true, DRM_MODE_ATOMIC_ALLOW_MODESET));
	for (plane = 0; plane < d.nplanes; plane++)
		for (i = 0; i < ARRAY_SIZE(property_names); i++)
			assert(written[plane][i] == d.planes[plane].original[i]);
	additions = 0;
	reject_addition = 4;
	assert(route(&d, 77, false, 0) < 0);
	assert(commits == 3 && frees == 4);
	/* Argument rejection must happen before opening a DRM device. */
	{
		char *args[] = { "probe", "hold", "cursor", "legacy", "1", "xrgb8888", NULL };
		assert(scanout_probe_main(6, args) == 2);
		args[2] = "primary";
		args[4] = "4294967297";
		assert(scanout_probe_main(6, args) == 2);
		args[4] = "0";
		assert(scanout_probe_main(6, args) == 2);
		args[4] = "600";
		args[5] = "invalid";
		assert(scanout_probe_main(6, args) == 2);
	}
	puts("PASS: actual plane routing and complete property restoration, preflight flags, failed-property cleanup and pre-device argument guards");
	return 0;
}
