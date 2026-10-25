// SPDX-License-Identifier: GPL-2.0-or-later
// Run a12-splash's KMS backend (B12 step 1) against a fake DRM device.
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <drm/drm.h>
#include <drm/drm_mode.h>
#include "../packages/a12-controls/sources/splash/splash-kms.h"

#ifndef DRM_IOCTL_MODE_CLOSEFB
#define DRM_IOCTL_MODE_CLOSEFB DRM_IOWR(0xD0, struct drm_mode_closefb)
#endif

static int connected = 1, fail_setcrtc, closed, unmapped;
static char calls[512];
static struct drm_mode_crtc set;
static uint32_t set_connector, closefb_id;
static void *buffer;

static void note(const char *s) { strcat(calls, s); strcat(calls, " "); }

static int fake_open(const char *path, int flags)
{
	(void)flags;
	assert(strcmp(path, "/dev/dri/card0") == 0);
	return 3;
}

static int fake_ioctl(int fd, unsigned long request, void *arg)
{
	assert(fd == 3);
	if (request == DRM_IOCTL_SET_MASTER) { note("master"); return 0; }
	if (request == DRM_IOCTL_DROP_MASTER) { note("drop"); return 0; }
	if (request == DRM_IOCTL_MODE_GETRESOURCES) {
		struct drm_mode_card_res *r = arg;
		if (r->connector_id_ptr) {
			((uint32_t *)(uintptr_t)r->connector_id_ptr)[0] = 51;
			((uint32_t *)(uintptr_t)r->crtc_id_ptr)[0] = 31;
			((uint32_t *)(uintptr_t)r->encoder_id_ptr)[0] = 41;
		}
		r->count_connectors = r->count_crtcs = r->count_encoders = 1;
		note("res");
		return 0;
	}
	if (request == DRM_IOCTL_MODE_GETCONNECTOR) {
		struct drm_mode_get_connector *c = arg;
		assert(c->connector_id == 51);
		c->connection = connected ? 1 : 2;
		if (c->modes_ptr) {
			struct drm_mode_modeinfo *m = (void *)(uintptr_t)c->modes_ptr;
			memset(m, 0, 2 * sizeof(*m));
			m[0].hdisplay = 800; m[0].vdisplay = 480;
			m[1].hdisplay = 1024; m[1].vdisplay = 600; m[1].type = DRM_MODE_TYPE_PREFERRED;
			((uint32_t *)(uintptr_t)c->encoders_ptr)[0] = 41;
		}
		c->count_modes = 2;
		c->count_encoders = 1;
		c->count_props = 3;	/* must be ignored: props_ptr is 0 */
		c->encoder_id = 41;
		note("conn");
		return 0;
	}
	if (request == DRM_IOCTL_MODE_GETENCODER) {
		struct drm_mode_get_encoder *e = arg;
		assert(e->encoder_id == 41);
		e->crtc_id = 31;
		return 0;
	}
	if (request == DRM_IOCTL_MODE_CREATE_DUMB) {
		struct drm_mode_create_dumb *d = arg;
		assert(d->width == 1024 && d->height == 600 && d->bpp == 32);
		d->handle = 7; d->pitch = 4096; d->size = 4096 * 600;
		note("dumb");
		return 0;
	}
	if (request == DRM_IOCTL_MODE_ADDFB) {
		struct drm_mode_fb_cmd *f = arg;
		assert(f->handle == 7 && f->pitch == 4096 && f->depth == 24 && f->bpp == 32);
		f->fb_id = 42;
		note("addfb");
		return 0;
	}
	if (request == DRM_IOCTL_MODE_MAP_DUMB) {
		((struct drm_mode_map_dumb *)arg)->offset = 0x1000;
		note("map");
		return 0;
	}
	if (request == DRM_IOCTL_MODE_SETCRTC) {
		set = *(struct drm_mode_crtc *)arg;
		set_connector = set.count_connectors ? *(uint32_t *)(uintptr_t)set.set_connectors_ptr : 0;
		note("setcrtc");
		if (fail_setcrtc) { errno = EACCES; return -1; }
		return 0;
	}
	if (request == DRM_IOCTL_MODE_CLOSEFB) {
		closefb_id = ((struct drm_mode_closefb *)arg)->fb_id;
		note("closefb");
		return 0;
	}
	if (request == DRM_IOCTL_MODE_RMFB) { note("rmfb"); return 0; }
	assert(!"unexpected ioctl");
	return -1;
}

static void *fake_mmap(void *addr, size_t len, int prot, int flags, int fd, off_t off)
{
	(void)addr; (void)prot; (void)flags;
	assert(fd == 3 && off == 0x1000 && len == 4096 * 600);
	buffer = malloc(len);
	memset(buffer, 0xAB, len);	/* must be cleared by the backend */
	return buffer;
}
static int fake_munmap(void *addr, size_t len) { (void)len; assert(addr == buffer); free(buffer); unmapped++; return 0; }
static int fake_close(int fd) { assert(fd == 3); closed++; note("close"); return 0; }

static void reset(void)
{
	calls[0] = 0; closed = unmapped = 0; fail_setcrtc = 0; connected = 1; closefb_id = 0;
	memset(&set, 0, sizeof(set));
}

int main(void)
{
	splash_kms_ops = (struct splash_kms_ops){ fake_open, fake_ioctl, fake_mmap, fake_munmap, fake_close };
	struct splash_kms k;
	struct splash_frame f;

	reset();
	assert(splash_kms_open(&k, &f, "/dev/dri/card0") == 0);
	assert(f.width == 1024 && f.height == 600 && f.stride_px == 1024);
	assert(f.px[0] == 0 && f.px[1024 * 600 - 1] == 0);
	assert(set.crtc_id == 31 && set.fb_id == 42 && set.mode_valid && set.mode.hdisplay == 1024);
	assert(set.count_connectors == 1 && set_connector == 51);
	f.px[0] = 0xFFFFFF;
	splash_kms_release(&k);
	/* The last frame stays: CLOSEFB (not RMFB), then drop master, then close. */
	assert(closefb_id == 42 && !strstr(calls, "rmfb"));
	assert(strstr(calls, "setcrtc closefb drop close"));
	assert(closed == 1 && unmapped == 1);

	/* --blank: disable the CRTC (no fb, no connectors), then release. */
	reset();
	assert(splash_kms_open(&k, &f, "/dev/dri/card0") == 0);
	assert(splash_kms_disable(&k) == 0);
	assert(set.crtc_id == 31 && set.fb_id == 0 && set.count_connectors == 0 && !set.mode_valid);
	splash_kms_release(&k);
	assert(strstr(calls, "setcrtc setcrtc closefb drop close"));

	/* Prepare, draw, then show (a12-update-splash, test 61): no SETCRTC
	 * before show, so the panel never scans out the cleared buffer. */
	reset();
	assert(splash_kms_prepare(&k, &f, "/dev/dri/card0") == 0);
	assert(!strstr(calls, "setcrtc") && f.px[0] == 0);
	f.px[0] = 0x123456;
	assert(splash_kms_show(&k) == 0);
	assert(set.crtc_id == 31 && set.fb_id == 42 && set.mode_valid && set.mode.hdisplay == 1024);
	assert(set_connector == 51 && f.px[0] == 0x123456);
	splash_kms_release(&k);
	assert(strstr(calls, "map setcrtc closefb drop close"));

	reset();
	connected = 0;
	assert(splash_kms_open(&k, &f, "/dev/dri/card0") != 0);
	assert(closed == 1 && !strstr(calls, "dumb"));	/* nothing allocated, fd closed */

	reset();
	fail_setcrtc = 1;	/* e.g. ES holds DRM master */
	assert(splash_kms_open(&k, &f, "/dev/dri/card0") != 0);
	assert(closed == 1 && unmapped == 1 && k.fd == -1);
	splash_kms_release(&k);	/* harmless after a failed open */
	assert(closed == 1);
	puts("splash kms: ok");
	return 0;
}
