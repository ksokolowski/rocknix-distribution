// SPDX-License-Identifier: GPL-2.0-or-later
/* Isolate scanout from GPU rendering. Buffers are filled before presentation
 * and never written again. This is a visual diagnostic, not a benchmark.
 */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include <drm_fourcc.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

#define WIDTH 1024
#define HEIGHT 600
#define MAX_PLANES 8
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
static const char *const property_names[] = {
	"FB_ID", "CRTC_ID", "CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H",
	"SRC_X", "SRC_Y", "SRC_W", "SRC_H"
};

struct plane {
	uint32_t id, type, possible;
	uint32_t properties[ARRAY_SIZE(property_names)];
	uint64_t original[ARRAY_SIZE(property_names)];
};

struct buffer {
	uint32_t handle, fb, pitch;
	uint64_t size, hash;
	void *map;
};

struct display {
	int fd;
	uint32_t connector, crtc;
	unsigned int crtc_index, nplanes;
	drmModeCrtc *saved;
	struct plane planes[MAX_PLANES];
	struct buffer buffers[2];
	bool changed, legacy;
	unsigned int selected;
};

static volatile sig_atomic_t stopped;
static bool flipped;
static uint64_t events, gaps, first_us, last_us, interval_min = UINT64_MAX;
static uint64_t interval_max, interval_sum;
static uint32_t first_sequence, last_sequence;

static void stop(int signum)
{
	(void)signum;
	stopped = 1;
}

static int install_stop_handlers(void)
{
	struct sigaction action = { .sa_handler = stop };
	sigemptyset(&action.sa_mask);
	return sigaction(SIGTERM, &action, NULL) ||
	       sigaction(SIGINT, &action, NULL) ||
	       sigaction(SIGHUP, &action, NULL) ? -1 : 0;
}

static uint64_t now_us(void)
{
	struct timespec time;
	clock_gettime(CLOCK_MONOTONIC, &time);
	return (uint64_t)time.tv_sec * 1000000 + time.tv_nsec / 1000;
}

static uint64_t hash_buffer(const struct buffer *b)
{
	const uint8_t *bytes = b->map;
	uint64_t hash = UINT64_C(14695981039346656037), i;
	for (i = 0; i < b->size; i++)
		hash = (hash ^ bytes[i]) * UINT64_C(1099511628211);
	return hash;
}

static uint32_t pixel(unsigned int x, unsigned int y, unsigned int phase)
{
	/* All channels >= 32: there are no intentional black lines or pixels. */
	unsigned int u = (x + phase * 32) % WIDTH;
	unsigned int r = 32 + ((u / 16 + y / 32) % 6) * 32;
	unsigned int g = 48 + ((u / 32 + y / 16) % 6) * 24;
	unsigned int b = 64 + ((u / 64 + y / 8) % 5) * 24;
	return UINT32_C(0xff000000) | r << 16 | g << 8 | b;
}

static void fill_buffer(struct buffer *b, uint32_t format, unsigned int phase)
{
	unsigned int x, y;
	memset(b->map, 0, b->size);
	for (y = 0; y < HEIGHT; y++) {
		uint8_t *row = (uint8_t *)b->map + (size_t)y * b->pitch;
		for (x = 0; x < WIDTH; x++) {
			uint32_t c = pixel(x, y, phase);
			if (format == DRM_FORMAT_RGB565)
				((uint16_t *)row)[x] = ((c >> 8) & 0xf800) |
					((c >> 5) & 0x07e0) | ((c >> 3) & 0x001f);
			else
				((uint32_t *)row)[x] = c;
		}
	}
	b->hash = hash_buffer(b);
}

static int verify_pixels(const struct buffer *b, uint32_t format, unsigned int phase)
{
	unsigned int x, y;
	uint64_t mismatches = 0;
	unsigned int bytes = format == DRM_FORMAT_RGB565 ? 2 : 4;
	for (y = 0; y < HEIGHT; y++) {
		const volatile uint8_t *row = (const volatile uint8_t *)b->map + (size_t)y * b->pitch;
		for (x = 0; x < WIDTH; x++) {
			uint32_t expected = pixel(x, y, phase), actual;
			if (bytes == 2) {
				expected = ((expected >> 8) & 0xf800) |
					   ((expected >> 5) & 0x07e0) | ((expected >> 3) & 0x001f);
				actual = ((const volatile uint16_t *)row)[x];
			} else
				actual = ((const volatile uint32_t *)row)[x];
			if (actual != expected) {
				if (mismatches < 8)
					fprintf(stderr, "pixel_mismatch x=%u y=%u expected=%08x actual=%08x\n",
						x, y, expected, actual);
				mismatches++;
			}
		}
		for (x = WIDTH * bytes; x < b->pitch; x++)
			if (row[x])
				mismatches++;
	}
	printf("buffer=%u expected_pixels=%s mismatches=%" PRIu64 "\n",
	       b->fb, mismatches ? "FAIL" : "PASS", mismatches);
	if (mismatches) {
		errno = EIO;
		return -1;
	}
	return 0;
}

static int self_test(void)
{
	unsigned int i, x, y;
	const uint32_t formats[] = { DRM_FORMAT_XRGB8888, DRM_FORMAT_ARGB8888,
				    DRM_FORMAT_RGB565 };
	for (i = 0; i < ARRAY_SIZE(formats); i++) {
		struct buffer b = { .pitch = WIDTH * (i == 2 ? 2 : 4) + 64 };
		uint64_t phase0;
		b.size = (uint64_t)b.pitch * HEIGHT;
		b.map = malloc(b.size);
		if (!b.map)
			return 1;
		fill_buffer(&b, formats[i], 0);
		phase0 = b.hash;
		for (y = 0; y < HEIGHT; y++) {
			const uint8_t *row = (uint8_t *)b.map + (size_t)y * b.pitch;
			for (x = 0; x < WIDTH; x++) {
				uint32_t expected = pixel(x, y, 0);
				if (i == 2) {
					uint16_t c = ((const uint16_t *)row)[x];
					if (((c >> 11) & 31) != ((expected >> 19) & 31) ||
					    ((c >> 5) & 63) != ((expected >> 10) & 63) ||
					    (c & 31) != ((expected >> 3) & 31))
						return 1;
				} else if (((const uint32_t *)row)[x] != expected)
					return 1;
				if ((expected & 0xffffff) == 0)
					return 1;
			}
			for (x = WIDTH * (i == 2 ? 2 : 4); x < b.pitch; x++)
				if (row[x])
					return 1;
		}
		fill_buffer(&b, formats[i], 0);
		if (b.hash != phase0)
			return 1;
		fill_buffer(&b, formats[i], 1);
		if (b.hash == phase0)
			return 1;
		free(b.map);
	}
	puts("PASS: opaque nonblack patterns, padded rows, RGB565 channel packing, identical and alternate image hashes");
	return 0;
}

static int discover(struct display *d)
{
	drmModeRes *resources = drmModeGetResources(d->fd);
	drmModePlaneRes *planes;
	unsigned int i, j, k;
	if (!resources)
		return -1;
	for (i = 0; i < (unsigned int)resources->count_connectors; i++) {
		drmModeConnector *c = drmModeGetConnector(d->fd, resources->connectors[i]);
		drmModeEncoder *encoder;
		if (!c)
			goto fail;
		if (c->connection != DRM_MODE_CONNECTED ||
		    c->connector_type != DRM_MODE_CONNECTOR_LVDS || !c->encoder_id) {
			drmModeFreeConnector(c);
			continue;
		}
		encoder = drmModeGetEncoder(d->fd, c->encoder_id);
		if (!encoder || !encoder->crtc_id || d->crtc) {
			drmModeFreeEncoder(encoder);
			drmModeFreeConnector(c);
			goto fail;
		}
		d->crtc = encoder->crtc_id;
		d->connector = c->connector_id;
		drmModeFreeEncoder(encoder);
		drmModeFreeConnector(c);
	}
	if (!d->crtc)
		goto fail;
	for (i = 0; i < (unsigned int)resources->count_crtcs; i++) {
		drmModeCrtc *crtc = drmModeGetCrtc(d->fd, resources->crtcs[i]);
		if (!crtc)
			goto fail;
		if (crtc->crtc_id == d->crtc) {
			d->saved = crtc;
			d->crtc_index = i;
		} else {
			bool active = crtc->mode_valid;
			drmModeFreeCrtc(crtc);
			if (active)
				goto fail;
		}
	}
	if (!d->saved || !d->saved->mode_valid || d->saved->mode.hdisplay != WIDTH ||
	    d->saved->mode.vdisplay != HEIGHT || d->saved->mode.htotal != 1354 ||
	    d->saved->mode.vtotal != 645 || d->saved->mode.clock != 75200 ||
	    d->saved->x || d->saved->y ||
	    (d->saved->mode.flags & (DRM_MODE_FLAG_INTERLACE | DRM_MODE_FLAG_DBLSCAN)))
		goto fail;
	drmModeFreeResources(resources);
	planes = drmModeGetPlaneResources(d->fd);
	if (!planes || planes->count_planes > MAX_PLANES) {
		drmModeFreePlaneResources(planes);
		return -1;
	}
	d->nplanes = planes->count_planes;
	for (i = 0; i < d->nplanes; i++) {
		struct plane *p = &d->planes[i];
		drmModePlane *plane = drmModeGetPlane(d->fd, planes->planes[i]);
		drmModeObjectProperties *properties;
		if (!plane)
			goto plane_fail;
		p->id = plane->plane_id;
		p->possible = plane->possible_crtcs;
		drmModeFreePlane(plane);
		properties = drmModeObjectGetProperties(d->fd, p->id, DRM_MODE_OBJECT_PLANE);
		if (!properties)
			goto plane_fail;
		for (j = 0; j < properties->count_props; j++) {
			drmModePropertyRes *property = drmModeGetProperty(d->fd, properties->props[j]);
			if (!property) {
				drmModeFreeObjectProperties(properties);
				goto plane_fail;
			}
			if (!strcmp(property->name, "type"))
				p->type = properties->prop_values[j];
			for (k = 0; k < ARRAY_SIZE(property_names); k++)
				if (!strcmp(property->name, property_names[k])) {
					p->properties[k] = property->prop_id;
					p->original[k] = properties->prop_values[j];
				}
			drmModeFreeProperty(property);
		}
		drmModeFreeObjectProperties(properties);
		for (k = 0; k < ARRAY_SIZE(property_names); k++)
			if (!p->properties[k])
				goto plane_fail;
		printf("plane=%u type=%u possible_crtcs=%#x original_fb=%" PRIu64
		       " original_crtc=%" PRIu64 "\n", p->id, p->type,
		       p->possible, p->original[0], p->original[1]);
	}
	drmModeFreePlaneResources(planes);
	printf("crtc=%u connector=%u native=%ux%u totals=%ux%u requested_clock_khz=%u\n",
	       d->crtc, d->connector, d->saved->mode.hdisplay, d->saved->mode.vdisplay,
	       d->saved->mode.htotal, d->saved->mode.vtotal, d->saved->mode.clock);
	return 0;
plane_fail:
	drmModeFreePlaneResources(planes);
	return -1;
fail:
	drmModeFreeResources(resources);
	errno = EINVAL;
	return -1;
}

static int allocate_buffer(struct display *d, struct buffer *b, uint32_t format,
			   unsigned int phase)
{
	struct drm_mode_create_dumb create = { .width = WIDTH, .height = HEIGHT,
		.bpp = format == DRM_FORMAT_RGB565 ? 16 : 32 };
	struct drm_mode_map_dumb map = { 0 };
	uint32_t handles[4] = { 0 }, pitches[4] = { 0 }, offsets[4] = { 0 };
	if (drmIoctl(d->fd, DRM_IOCTL_MODE_CREATE_DUMB, &create))
		return -1;
	b->handle = handles[0] = create.handle;
	b->pitch = pitches[0] = create.pitch;
	b->size = create.size;
	if (b->size < (uint64_t)b->pitch * HEIGHT ||
	    b->pitch < WIDTH * (format == DRM_FORMAT_RGB565 ? 2u : 4u)) {
		errno = EINVAL;
		return -1;
	}
	if (drmModeAddFB2(d->fd, WIDTH, HEIGHT, format, handles, pitches, offsets, &b->fb, 0))
		return -1;
	map.handle = b->handle;
	if (drmIoctl(d->fd, DRM_IOCTL_MODE_MAP_DUMB, &map))
		return -1;
	b->map = mmap(NULL, b->size, PROT_READ | PROT_WRITE, MAP_SHARED, d->fd, map.offset);
	if (b->map == MAP_FAILED) {
		b->map = NULL;
		return -1;
	}
	fill_buffer(b, format, phase);
	/* Prevent even accidental userspace writes after presentation starts. */
	if (mprotect(b->map, b->size, PROT_READ))
		return -1;
	printf("buffer=%u handle=%u pitch=%u size=%" PRIu64 " map_offset=%" PRIu64 " hash=%016" PRIx64 "\n",
	       b->fb, b->handle, b->pitch, b->size, (uint64_t)map.offset, b->hash);
	if (verify_pixels(b, format, phase))
		return -1;
	if (hash_buffer(b) != b->hash) {
		fprintf(stderr, "buffer=%u checksum changed during initial readback\n", b->fb);
		errno = EIO;
		return -1;
	}
	return 0;
}

static int route(struct display *d, uint32_t fb, bool restore, uint32_t flags)
{
	drmModeAtomicReq *request = drmModeAtomicAlloc();
	unsigned int i, k;
	int result = -1;
	if (!request)
		return -1;
	for (i = 0; i < d->nplanes; i++) {
		struct plane *p = &d->planes[i];
		uint64_t values[ARRAY_SIZE(property_names)] = { 0 };
		if (restore)
			memcpy(values, p->original, sizeof(values));
		else if (i == d->selected) {
			values[0] = fb;
			values[1] = d->crtc;
			values[4] = WIDTH;
			values[5] = HEIGHT;
			values[8] = WIDTH << 16;
			values[9] = HEIGHT << 16;
		}
		for (k = 0; k < ARRAY_SIZE(property_names); k++)
			if (drmModeAtomicAddProperty(request, p->id, p->properties[k], values[k]) < 0)
				goto out;
	}
	result = drmModeAtomicCommit(d->fd, request, flags, NULL);
out:
	drmModeAtomicFree(request);
	return result;
}

static void event(int fd, unsigned int sequence, unsigned int sec,
		  unsigned int usec, void *data)
{
	uint64_t stamp = (uint64_t)sec * 1000000 + usec;
	(void)fd;
	(void)data;
	flipped = true;
	if (!events) {
		first_us = stamp;
		first_sequence = sequence;
	} else {
		uint64_t interval = stamp - last_us;
		if ((uint32_t)(sequence - last_sequence) != 1)
			gaps++;
		if (interval < interval_min)
			interval_min = interval;
		if (interval > interval_max)
			interval_max = interval;
		interval_sum += interval;
	}
	last_us = stamp;
	last_sequence = sequence;
	events++;
}

static int wait_flip(struct display *d)
{
	uint64_t deadline = now_us() + 3000000;
	drmEventContext context = { .version = 2, .page_flip_handler = event };
	while (!flipped && now_us() < deadline) {
		struct pollfd p = { .fd = d->fd, .events = POLLIN };
		int result = poll(&p, 1, 100);
		if (result < 0 && errno != EINTR)
			return -1;
		if (result > 0 && (p.revents & (POLLERR | POLLHUP | POLLNVAL)))
			return -1;
		if (result > 0 && (p.revents & POLLIN) && drmHandleEvent(d->fd, &context))
			return -1;
	}
	if (!flipped) {
		errno = ETIMEDOUT;
		return -1;
	}
	return 0;
}

static int cleanup(struct display *d)
{
	unsigned int i;
	int result = 0;
	if (d->changed) {
		if (d->legacy)
			result = drmModeSetCrtc(d->fd, d->crtc, d->saved->buffer_id,
				0, 0, &d->connector, 1, &d->saved->mode);
		else
			result = route(d, 0, true, DRM_MODE_ATOMIC_ALLOW_MODESET);
		printf("original_scanout_restore=%s\n", result ? "FAILED" : "success");
	}
	for (i = 0; i < ARRAY_SIZE(d->buffers); i++) {
		struct buffer *b = &d->buffers[i];
		if (b->map) {
			bool unchanged = hash_buffer(b) == b->hash;
			printf("buffer=%u immutable_hash=%s\n", b->fb, unchanged ? "PASS" : "FAIL");
			if (!unchanged)
				result = -1;
			munmap(b->map, b->size);
		}
		if (b->fb)
			drmModeRmFB(d->fd, b->fb);
		if (b->handle) {
			struct drm_mode_destroy_dumb destroy = { .handle = b->handle };
			drmIoctl(d->fd, DRM_IOCTL_MODE_DESTROY_DUMB, &destroy);
		}
	}
	drmModeFreeCrtc(d->saved);
	if (d->fd >= 0)
		close(d->fd);
	return result;
}

int main(int argc, char **argv)
{
	struct display d = { .fd = -1 };
	uint32_t format, wanted_type;
	unsigned int seconds, i, found = 0, next = 1;
	unsigned long requested_seconds;
	uint64_t deadline;
	int result = 1;
	char *end;
	bool allocation_test = argc == 2 && !strcmp(argv[1], "allocate-check");
	bool inspect = argc == 2 && (!strcmp(argv[1], "inspect") || allocation_test);
	bool hold;
	if (argc == 2 && !strcmp(argv[1], "self-test"))
		return self_test();
	if (!inspect && (argc != 6 ||
	    (strcmp(argv[1], "hold") && strcmp(argv[1], "identical") && strcmp(argv[1], "alternate")) ||
	    (strcmp(argv[2], "primary") && strcmp(argv[2], "cursor")) ||
	    (strcmp(argv[3], "legacy") && strcmp(argv[3], "atomic"))))
		goto usage;
	wanted_type = inspect || !strcmp(argv[2], "primary") ?
		DRM_PLANE_TYPE_PRIMARY : DRM_PLANE_TYPE_CURSOR;
	d.legacy = !inspect && !strcmp(argv[3], "legacy");
	if (d.legacy && wanted_type != DRM_PLANE_TYPE_PRIMARY)
		goto usage;
	errno = 0;
	requested_seconds = inspect ? 0 : strtoul(argv[4], &end, 10);
	if (!inspect && (errno || !*argv[4] || *end || requested_seconds < 1 || requested_seconds > 600))
		goto usage;
	seconds = requested_seconds;
	format = inspect || !strcmp(argv[5], "xrgb8888") ? DRM_FORMAT_XRGB8888 :
		!strcmp(argv[5], "argb8888") ? DRM_FORMAT_ARGB8888 :
		!strcmp(argv[5], "rgb565") ? DRM_FORMAT_RGB565 : 0;
	if (!format)
		goto usage;
	setvbuf(stdout, NULL, _IOLBF, 0);
	d.fd = open("/dev/dri/card0", O_RDWR | O_CLOEXEC);
	if (d.fd < 0)
		goto fail;
	if (drmSetClientCap(d.fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1) ||
	    drmSetClientCap(d.fd, DRM_CLIENT_CAP_ATOMIC, 1) || discover(&d))
		goto fail;
	if (inspect) {
		if (allocation_test) {
			for (i = 0; i < ARRAY_SIZE(d.buffers); i++)
				if (allocate_buffer(&d, &d.buffers[i], DRM_FORMAT_XRGB8888, 0))
					goto fail;
			if (d.buffers[0].hash != d.buffers[1].hash) {
				fprintf(stderr, "Identical allocations have different checksums.\n");
				goto out;
			}
			puts("PASS: identical allocations match expected pixels/checksums; scanout untouched");
		}
		result = 0;
		goto out;
	}
	if (!drmIsMaster(d.fd)) {
		fprintf(stderr, "Stop the frontend/game first; another DRM master owns scanout.\n");
		goto out;
	}
	for (i = 0; i < d.nplanes; i++) {
		struct plane *p = &d.planes[i];
		if (p->type == wanted_type && (p->possible & (1u << d.crtc_index))) {
			d.selected = i;
			found++;
		}
		/* The wrapper requires fbcon before acquiring DRM master. */
		if (p->original[0] && p->type != DRM_PLANE_TYPE_PRIMARY) {
			fprintf(stderr, "Refusing to replace an already-active overlay/cursor.\n");
			goto out;
		}
	}
	if (found != 1) {
		fprintf(stderr, "Expected exactly one compatible selected plane.\n");
		goto out;
	}
	hold = !strcmp(argv[1], "hold");
	for (i = 0; i < ARRAY_SIZE(d.buffers); i++)
		if (allocate_buffer(&d, &d.buffers[i], format,
				    i && !strcmp(argv[1], "alternate")))
			goto fail;
	if (install_stop_handlers())
		goto fail;
	printf("scenario=%s plane=%u type=%u api=%s format=%s seconds=%u GPU=unused uploads=none buffers=immutable\n",
	       argv[1], d.planes[d.selected].id, wanted_type, argv[3], argv[5], seconds);
	if (d.legacy) {
		if (drmModeSetCrtc(d.fd, d.crtc, d.buffers[0].fb, 0, 0,
				   &d.connector, 1, &d.saved->mode))
			goto fail;
	} else {
		if (route(&d, d.buffers[0].fb, false,
			  DRM_MODE_ATOMIC_TEST_ONLY | DRM_MODE_ATOMIC_ALLOW_MODESET))
			goto fail;
		if (route(&d, d.buffers[0].fb, false, DRM_MODE_ATOMIC_ALLOW_MODESET))
			goto fail;
	}
	d.changed = true;
	puts("READY: observe this single scenario; there are no intended black pixels.");
	deadline = now_us() + (uint64_t)seconds * 1000000;
	while (!stopped && now_us() < deadline) {
		if (hold) {
			const struct timespec delay = { .tv_nsec = 100000000 };
			nanosleep(&delay, NULL);
			continue;
		}
		flipped = false;
		if (d.legacy) {
			if (drmModePageFlip(d.fd, d.crtc, d.buffers[next].fb,
					    DRM_MODE_PAGE_FLIP_EVENT, NULL))
				goto fail;
		} else if (route(&d, d.buffers[next].fb, false,
				 DRM_MODE_ATOMIC_NONBLOCK | DRM_MODE_PAGE_FLIP_EVENT))
			goto fail;
		/* Never reuse/release a displayed buffer before flip completion. */
		if (wait_flip(&d))
			goto fail;
		next ^= 1;
	}
	printf("events=%" PRIu64 " sequence_gaps=%" PRIu64, events, gaps);
	if (events > 1 && last_us > first_us)
		printf(" observed_hz=%.6f interval_us_min=%" PRIu64 " mean=%.3f max=%" PRIu64,
		       (double)(uint32_t)(last_sequence - first_sequence) * 1000000 / (last_us - first_us),
		       interval_min, (double)interval_sum / (events - 1), interval_max);
	putchar('\n');
	result = 0;
	goto out;
fail:
	perror("scanout probe");
out:
	if (cleanup(&d))
		result = 1;
	return result;
usage:
	fprintf(stderr, "usage: %s inspect|self-test|allocate-check\n"
		"       %s hold|identical|alternate primary|cursor legacy|atomic SECONDS xrgb8888|argb8888|rgb565\n",
		argv[0], argv[0]);
	return 2;
}
