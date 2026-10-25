// SPDX-License-Identifier: GPL-2.0-or-later
#include <fcntl.h>
#include <libgen.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "splash-fb.h"

int splash_fb_supported(int xres, int yres, int bpp, int line_length)
{
	/* The A12 panel mode only; anything else (HDMI, RGB565) keeps today's boot. */
	return xres == 1024 && yres == 600 && bpp == 32 && line_length == 4096;
}

int splash_logo_needs_capture(const char *stamp_path, const char *build_id_line)
{
	char line[256] = "";
	FILE *f = fopen(stamp_path, "r");
	if (!f)
		return 1;
	if (!fgets(line, sizeof(line), f))
		line[0] = 0;
	fclose(f);
	line[strcspn(line, "\n")] = 0;
	return strcmp(line, build_id_line) != 0;
}

double splash_read_seconds(const char *path)
{
	char line[64] = "";
	char *end;
	FILE *f = fopen(path, "r");
	if (!f)
		return 0;
	if (!fgets(line, sizeof(line), f))
		line[0] = 0;
	fclose(f);
	double v = strtod(line, &end);
	if (end == line || v < 1 || v > 300)
		return 0;
	return v;
}

int splash_write_seconds(const char *path, double seconds)
{
	FILE *f = fopen(path, "w");
	if (!f)
		return -1;
	fprintf(f, "%.1f\n", seconds);
	return splash_close_synced(f);
}

int splash_close_synced(FILE *f)
{
	int ok = fflush(f) == 0;
	ok &= fsync(fileno(f)) == 0;
	ok &= fclose(f) == 0;
	return ok ? 0 : -1;
}

int splash_sync_dir(const char *path)
{
	char copy[PATH_MAX];
	snprintf(copy, sizeof(copy), "%s", path);
	int fd = open(dirname(copy), O_RDONLY | O_DIRECTORY);
	if (fd < 0)
		return -1;
	int r = fsync(fd);
	close(fd);
	return r;
}

int splash_cmdline_has(const char *path, const char *word)
{
	char line[4096];
	size_t n = strlen(word);
	FILE *f = fopen(path, "r");
	if (!f)
		return 0;
	if (!fgets(line, sizeof(line), f))
		line[0] = 0;
	fclose(f);
	for (char *p = line; (p = strstr(p, word)); p += n)
		if ((p == line || p[-1] == ' ') && (p[n] == 0 || p[n] == ' ' || p[n] == '\n'))
			return 1;
	return 0;
}
