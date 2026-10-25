// SPDX-License-Identifier: GPL-2.0-or-later
// A12 splash on a KMS dumb buffer (B12 step 1, plan 2026-10-11-a12-drm-splash-and-uboot-logo).
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <drm/drm.h>
#include <drm/drm_mode.h>
#include "splash-kms.h"

#ifndef DRM_IOCTL_MODE_CLOSEFB
struct drm_mode_closefb { __u32 fb_id; __u32 pad; };
#define DRM_IOCTL_MODE_CLOSEFB DRM_IOWR(0xD0, struct drm_mode_closefb)
#endif

static int sys_open(const char *path, int flags) { return open(path, flags); }
static int sys_ioctl(int fd, unsigned long request, void *arg) { return ioctl(fd, request, arg); }

struct splash_kms_ops splash_kms_ops = { sys_open, sys_ioctl, mmap, munmap, close };

static int xioctl(int fd, unsigned long request, void *arg)
{
	int r;
	do
		r = splash_kms_ops.ioctl(fd, request, arg);
	while (r == -1 && (errno == EINTR || errno == EAGAIN));
	return r;
}

static uint64_t ptr(void *p) { return (uint64_t)(uintptr_t)p; }

/* Connected connector with a mode; fills mode (preferred, else first). */
static int pick_connector(int fd, const struct drm_mode_card_res *res, const uint32_t *connectors,
			  struct drm_mode_get_connector *out, struct drm_mode_modeinfo *mode)
{
	for (uint32_t i = 0; i < res->count_connectors; i++) {
		struct drm_mode_get_connector c = { .connector_id = connectors[i] };
		if (xioctl(fd, DRM_IOCTL_MODE_GETCONNECTOR, &c) || c.connection != 1 || !c.count_modes)
			continue;
		struct drm_mode_modeinfo *modes = calloc(c.count_modes, sizeof(*modes));
		uint32_t *encoders = calloc(c.count_encoders ? c.count_encoders : 1, sizeof(*encoders));
		uint32_t count_modes = c.count_modes;
		c.modes_ptr = ptr(modes);
		c.encoders_ptr = ptr(encoders);
		c.count_props = 0;
		c.props_ptr = c.prop_values_ptr = 0;
		int ok = modes && encoders && !xioctl(fd, DRM_IOCTL_MODE_GETCONNECTOR, &c) &&
			 c.count_modes && c.count_modes <= count_modes;
		if (ok) {
			*mode = modes[0];
			for (uint32_t m = 0; m < c.count_modes; m++)
				if (modes[m].type & DRM_MODE_TYPE_PREFERRED) {
					*mode = modes[m];
					break;
				}
			*out = c;
		}
		free(modes);
		free(encoders);
		if (ok)
			return 0;
	}
	return -1;
}

_Static_assert(sizeof(((struct splash_kms *)0)->mode) == sizeof(struct drm_mode_modeinfo),
	       "splash_kms.mode holds a struct drm_mode_modeinfo");

/* Undo a partial or failed setup: unmap, close, mark closed. */
static void discard(struct splash_kms *k)
{
	if (k->map)
		splash_kms_ops.munmap(k->map, k->size);
	if (k->fd >= 0)
		splash_kms_ops.close(k->fd);
	memset(k, 0, sizeof(*k));
	k->fd = -1;
}

int splash_kms_prepare(struct splash_kms *k, struct splash_frame *frame, const char *card)
{
	memset(k, 0, sizeof(*k));
	k->fd = splash_kms_ops.open(card, O_RDWR | O_CLOEXEC);
	if (k->fd < 0)
		return -1;
	xioctl(k->fd, DRM_IOCTL_SET_MASTER, NULL);	/* usually implicit on first open */

	struct drm_mode_card_res res = { 0 };
	if (xioctl(k->fd, DRM_IOCTL_MODE_GETRESOURCES, &res) || !res.count_connectors || !res.count_crtcs)
		goto fail;
	uint32_t *connectors = calloc(res.count_connectors, sizeof(uint32_t));
	uint32_t *crtcs = calloc(res.count_crtcs, sizeof(uint32_t));
	uint32_t *encoders = calloc(res.count_encoders ? res.count_encoders : 1, sizeof(uint32_t));
	struct drm_mode_card_res fill = { .connector_id_ptr = ptr(connectors), .crtc_id_ptr = ptr(crtcs),
					  .encoder_id_ptr = ptr(encoders), .count_connectors = res.count_connectors,
					  .count_crtcs = res.count_crtcs, .count_encoders = res.count_encoders };
	struct drm_mode_get_connector conn;
	struct drm_mode_modeinfo mode;
	int ok = connectors && crtcs && encoders && !xioctl(k->fd, DRM_IOCTL_MODE_GETRESOURCES, &fill) &&
		 !pick_connector(k->fd, &fill, connectors, &conn, &mode);
	if (ok) {
		k->connector_id = conn.connector_id;
		struct drm_mode_get_encoder enc = { .encoder_id = conn.encoder_id };
		if (conn.encoder_id && !xioctl(k->fd, DRM_IOCTL_MODE_GETENCODER, &enc) && enc.crtc_id)
			k->crtc_id = enc.crtc_id;
		else
			k->crtc_id = crtcs[0];
	}
	free(connectors);
	free(crtcs);
	free(encoders);
	if (!ok)
		goto fail;

	struct drm_mode_create_dumb dumb = { .width = mode.hdisplay, .height = mode.vdisplay, .bpp = 32 };
	if (xioctl(k->fd, DRM_IOCTL_MODE_CREATE_DUMB, &dumb))
		goto fail;
	k->handle = dumb.handle;
	k->size = (size_t)dumb.size;
	struct drm_mode_fb_cmd fb = { .width = mode.hdisplay, .height = mode.vdisplay, .pitch = dumb.pitch,
				      .bpp = 32, .depth = 24, .handle = dumb.handle };
	if (xioctl(k->fd, DRM_IOCTL_MODE_ADDFB, &fb))
		goto fail;
	k->fb_id = fb.fb_id;
	struct drm_mode_map_dumb map = { .handle = dumb.handle };
	if (xioctl(k->fd, DRM_IOCTL_MODE_MAP_DUMB, &map))
		goto fail;
	k->map = splash_kms_ops.mmap(NULL, k->size, PROT_READ | PROT_WRITE, MAP_SHARED, k->fd, (off_t)map.offset);
	if (k->map == MAP_FAILED) {
		k->map = NULL;
		goto fail;
	}
	memset(k->map, 0, k->size);
	memcpy(k->mode, &mode, sizeof(mode));
	frame->px = k->map;
	frame->width = mode.hdisplay;
	frame->height = mode.vdisplay;
	frame->stride_px = (int)(dumb.pitch / 4);
	return 0;
fail:
	discard(k);
	return -1;
}

int splash_kms_show(struct splash_kms *k)
{
	struct drm_mode_crtc crtc = { .set_connectors_ptr = ptr(&k->connector_id), .count_connectors = 1,
				      .crtc_id = k->crtc_id, .fb_id = k->fb_id, .mode_valid = 1 };
	memcpy(&crtc.mode, k->mode, sizeof(crtc.mode));
	if (xioctl(k->fd, DRM_IOCTL_MODE_SETCRTC, &crtc)) {
		discard(k);
		return -1;
	}
	return 0;
}

int splash_kms_open(struct splash_kms *k, struct splash_frame *frame, const char *card)
{
	if (splash_kms_prepare(k, frame, card))
		return -1;
	return splash_kms_show(k);
}

int splash_kms_disable(struct splash_kms *k)
{
	struct drm_mode_crtc crtc = { .crtc_id = k->crtc_id };	/* no fb, no connectors */
	return xioctl(k->fd, DRM_IOCTL_MODE_SETCRTC, &crtc);
}

void splash_kms_release(struct splash_kms *k)
{
	if (k->fd < 0)
		return;
	if (k->fb_id) {
		struct drm_mode_closefb close_fb = { .fb_id = k->fb_id };
		xioctl(k->fd, DRM_IOCTL_MODE_CLOSEFB, &close_fb);
	}
	xioctl(k->fd, DRM_IOCTL_DROP_MASTER, NULL);
	if (k->map)
		splash_kms_ops.munmap(k->map, k->size);
	splash_kms_ops.close(k->fd);
	k->fd = -1;
}
