// SPDX-License-Identifier: GPL-2.0-or-later
// Play a video through libVLC the way ES's VideoVlcComponent does (RGBA vmem
// callbacks, start-time 0.7), silently (dummy audio output), N times.
// Extra arguments go to libvlc_new(), e.g. --avcodec-threads=2 (logging
// stays off: --quiet wins over -v).
// Usage: a12-vlcplay FILE SECONDS LOOPS [VLC-OPTION...]
#include <vlc/vlc.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}

#define W 384
#define H 224
static unsigned char pixels[W * H * 4];
static long frames;
static void *lock_cb(void *opaque, void **planes) { (void)opaque; planes[0] = pixels; return NULL; }
static void unlock_cb(void *opaque, void *picture, void *const *planes) { (void)opaque; (void)picture; (void)planes; }
static void display_cb(void *opaque, void *picture) { (void)opaque; (void)picture; frames++; }

int main(int argc, char **argv)
{
	if (argc < 4) { fprintf(stderr, "usage: %s FILE SECONDS LOOPS [VLC-OPTION...]\n", argv[0]); return 2; }
	const char *args[16] = { "--quiet", "--no-video-title-show", "--aout=adummy" };
	int nargs = 3;
	for (int i = 4; i < argc && nargs < 16; i++)
		args[nargs++] = argv[i];
	libvlc_instance_t *vlc = libvlc_new(nargs, args);
	if (!vlc) { fprintf(stderr, "libvlc_new failed\n"); return 1; }
	for (int l = 0; l < atoi(argv[3]); l++) {
		libvlc_media_t *m = libvlc_media_new_path(vlc, argv[1]);
		libvlc_media_add_option(m, ":start-time=0.7");
		libvlc_media_player_t *p = libvlc_media_player_new_from_media(m);
		libvlc_audio_set_mute(p, 1);
		libvlc_video_set_callbacks(p, lock_cb, unlock_cb, display_cb, NULL);
		libvlc_video_set_format(p, "RGBA", W, H, W * 4);
		libvlc_media_player_play(p);
		usleep(atoi(argv[2]) * 1000000);
		double t0 = now();
		libvlc_media_player_stop(p);
		double t1 = now();
		libvlc_media_player_release(p);
		libvlc_media_release(m);
		double t2 = now();
		printf("loop %d: %ld frames, stop %.3f s, release %.3f s\n", l, frames, t1 - t0, t2 - t1);
		fflush(stdout);
	}
	libvlc_release(vlc);
	return 0;
}
