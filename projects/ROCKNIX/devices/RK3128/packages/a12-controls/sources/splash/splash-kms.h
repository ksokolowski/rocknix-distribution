/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SPLASH_KMS_H
#define SPLASH_KMS_H
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#include "splash-draw.h"

/* KMS dumb-buffer surface for a12-splash (B12 step 1). Used only when there
 * is no /dev/fb0 or A12_SPLASH_FORCE_KMS=1; raw UAPI ioctls, no libdrm. */
struct splash_kms {
	int fd;
	uint32_t fb_id, handle, crtc_id, connector_id;
	size_t size;
	void *map;
	unsigned char mode[68];	/* struct drm_mode_modeinfo, set by prepare */
};

/* Replaceable for tests. */
struct splash_kms_ops {
	int (*open)(const char *path, int flags);
	int (*ioctl)(int fd, unsigned long request, void *arg);
	void *(*mmap)(void *addr, size_t length, int prot, int flags, int fd, off_t offset);
	int (*munmap)(void *addr, size_t length);
	int (*close)(int fd);
};
extern struct splash_kms_ops splash_kms_ops;

/* Light the first connected connector with its preferred mode and point
 * frame at a cleared XRGB8888 buffer. 0 on success. */
int splash_kms_open(struct splash_kms *k, struct splash_frame *frame, const char *card);
/* The same in two steps, so a frame can be drawn before it is shown (no
 * black flash when a new process replaces the previous frame): prepare
 * leaves the display alone; show scans the buffer out. 0 on success; on a
 * failed show the surface is released. */
int splash_kms_prepare(struct splash_kms *k, struct splash_frame *frame, const char *card);
int splash_kms_show(struct splash_kms *k);
/* Turn the display off: disable the CRTC (panel and VOP power down). */
int splash_kms_disable(struct splash_kms *k);
/* Leave the last frame on screen (CLOSEFB keeps the plane scanning it out),
 * drop DRM master so ES can take it, and close. */
void splash_kms_release(struct splash_kms *k);
#endif
