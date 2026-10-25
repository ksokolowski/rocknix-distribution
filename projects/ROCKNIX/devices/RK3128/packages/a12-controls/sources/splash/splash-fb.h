/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SPLASH_FB_H
#define SPLASH_FB_H
int splash_fb_supported(int xres, int yres, int bpp, int line_length);
int splash_logo_needs_capture(const char *stamp_path, const char *build_id_line);
/* Seconds from splash start to ES start on the previous boot; 0 if unknown
 * or outside 1..300 s. */
double splash_read_seconds(const char *path);
int splash_write_seconds(const char *path, double seconds);
#include <stdio.h>
/* fflush, fsync and fclose; 0 only if all succeed. */
int splash_close_synced(FILE *f);
/* fsync the directory holding path, so a rename into it is durable. */
int splash_sync_dir(const char *path);
/* 1 if the kernel command line in path holds word as a whole token. */
int splash_cmdline_has(const char *path, const char *word);
#endif
