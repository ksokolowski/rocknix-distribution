// SPDX-License-Identifier: GPL-2.0-or-later
/* Presentation cadence of whatever owns the display: wait for every vblank as
 * a passive DRM client and note when the primary plane's framebuffer changes.
 * Intervals between changes, in vblanks, show dropped frames and judder.
 * A client commits at most once per refresh period (each commit waits for the
 * previous flip), but often right after the vblank event. The plane is read
 * half a period after each vblank so that commit is not missed.
 * Usage: a12-present-probe SECONDS [INTERVALS_FILE]
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

#define MAX_BUCKET 8

static volatile sig_atomic_t stop;

static void on_signal(int sig)
{
	(void)sig;
	stop = 1;
}

static int is_primary(int fd, uint32_t plane_id)
{
	drmModeObjectProperties *props;
	int primary = 0;

	props = drmModeObjectGetProperties(fd, plane_id, DRM_MODE_OBJECT_PLANE);
	if (!props)
		return 0;
	for (uint32_t i = 0; i < props->count_props; i++) {
		drmModePropertyRes *p = drmModeGetProperty(fd, props->props[i]);

		if (p && !strcmp(p->name, "type") && props->prop_values[i] == DRM_PLANE_TYPE_PRIMARY)
			primary = 1;
		drmModeFreeProperty(p);
	}
	drmModeFreeObjectProperties(props);
	return primary;
}

int main(int argc, char **argv)
{
	unsigned long hist[MAX_BUCKET + 1] = { 0 };
	double seconds, t0 = 0, t = 0, sum = 0, sum2 = 0, max_ms = 0;
	uint32_t crtc_id = 0, plane_id = 0, pipe = 0, last_fb = 0;
	long half_period_ns = 0;
	unsigned int first_seq = 0, seq = 0, last_change = 0, missed = 0, prev_seq = 0;
	unsigned long changes = 0, intervals = 0;
	double last_change_t = 0;
	FILE *log = NULL;
	drmModeRes *res;
	drmModePlaneRes *planes;
	int fd;

	if (argc < 2 || (seconds = atof(argv[1])) <= 0) {
		fprintf(stderr, "usage: %s SECONDS [INTERVALS_FILE]\n", argv[0]);
		return 2;
	}
	if (argc > 2 && !(log = fopen(argv[2], "w"))) {
		perror(argv[2]);
		return 1;
	}
	fd = open("/dev/dri/card0", O_RDWR | O_CLOEXEC);
	if (fd < 0 || drmSetClientCap(fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1)) {
		perror("card0");
		return 1;
	}
	res = drmModeGetResources(fd);
	for (int i = 0; res && i < res->count_crtcs && !crtc_id; i++) {
		drmModeCrtc *c = drmModeGetCrtc(fd, res->crtcs[i]);

		if (c && c->mode_valid) {
			crtc_id = c->crtc_id;
			pipe = i;
			half_period_ns = (long)(5e8 * c->mode.htotal * c->mode.vtotal /
						(c->mode.clock * 1e3));
		}
		drmModeFreeCrtc(c);
	}
	planes = drmModeGetPlaneResources(fd);
	for (uint32_t i = 0; planes && i < planes->count_planes && !plane_id; i++) {
		drmModePlane *p = drmModeGetPlane(fd, planes->planes[i]);

		if (p && p->crtc_id == crtc_id && is_primary(fd, p->plane_id))
			plane_id = p->plane_id;
		drmModeFreePlane(p);
	}
	if (!crtc_id || !plane_id) {
		fprintf(stderr, "no active CRTC or primary plane\n");
		return 1;
	}
	signal(SIGINT, on_signal);
	signal(SIGTERM, on_signal);
	for (;;) {
		drmVBlank vbl = { 0 };
		drmModePlane *p;
		uint32_t fb;

		vbl.request.type = DRM_VBLANK_RELATIVE |
			((pipe << DRM_VBLANK_HIGH_CRTC_SHIFT) & DRM_VBLANK_HIGH_CRTC_MASK);
		vbl.request.sequence = 1;
		if (drmWaitVBlank(fd, &vbl)) {
			if (errno == EINTR && !stop)
				continue;
			break;
		}
		{
			/* vblank timestamps are CLOCK_MONOTONIC */
			struct timespec at = {
				.tv_sec = vbl.reply.tval_sec,
				.tv_nsec = vbl.reply.tval_usec * 1000L + half_period_ns,
			};

			if (at.tv_nsec >= 1000000000L) {
				at.tv_sec++;
				at.tv_nsec -= 1000000000L;
			}
			while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &at, NULL) == EINTR && !stop)
				;
		}
		p = drmModeGetPlane(fd, plane_id);
		fb = p ? p->fb_id : 0;
		drmModeFreePlane(p);
		seq = vbl.reply.sequence;
		t = vbl.reply.tval_sec + vbl.reply.tval_usec / 1e6;
		if (!t0) {
			t0 = t;
			first_seq = seq;
			last_fb = fb;
			last_change = seq;
			last_change_t = t;
		} else {
			if (seq - prev_seq > 1)
				missed += seq - prev_seq - 1;
			if (fb != last_fb) {
				unsigned int n = seq - last_change;
				double ms = (t - last_change_t) * 1e3;

				/* The first change only starts the clock. */
				if (changes) {
					hist[n > MAX_BUCKET ? MAX_BUCKET : n]++;
					intervals++;
					sum += ms;
					sum2 += ms * ms;
					if (ms > max_ms)
						max_ms = ms;
					if (log)
						fprintf(log, "%u %.3f\n", n, ms);
				}
				changes++;
				last_fb = fb;
				last_change = seq;
				last_change_t = t;
			}
		}
		prev_seq = seq;
		if (stop || t - t0 >= seconds)
			break;
	}
	if (log)
		fclose(log);
	if (seq == first_seq) {
		fprintf(stderr, "no vblanks\n");
		return 1;
	}
	{
		double span = t - t0, hz = (seq - first_seq) / span;
		double mean = intervals ? sum / intervals : 0;
		double sd = intervals ? sqrt(fmax(sum2 / intervals - mean * mean, 0)) : 0;

		printf("refresh_hz=%.3f vblanks=%u missed_samples=%u seconds=%.2f\n",
		       hz, seq - first_seq, missed, span);
		printf("presented=%lu presented_fps=%.3f interval_mean_ms=%.3f interval_sd_ms=%.3f interval_max_ms=%.3f\n",
		       intervals, intervals / span, mean, sd, max_ms);
		printf("interval_vblanks:");
		for (int i = 1; i <= MAX_BUCKET; i++)
			printf(" %d%s=%lu", i, i == MAX_BUCKET ? "+" : "", hist[i]);
		printf("\n");
	}
	return 0;
}
