// SPDX-License-Identifier: GPL-2.0-or-later
// Host test for a12-splash helpers (Task 4 of the boot splash plan).
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../packages/a12-controls/sources/splash/splash-fb.h"

static void test_rejects_unsupported_fb(void)
{
	assert(splash_fb_supported(1024, 600, 32, 4096));
	assert(!splash_fb_supported(1024, 600, 16, 2048));
	assert(!splash_fb_supported(1920, 1080, 32, 7680));
	assert(!splash_fb_supported(1024, 600, 32, 1000));
}

static void test_logo_capture_stamp(void)
{
	char path[] = "/tmp/splash-stamp-XXXXXX";
	int fd = mkstemp(path);
	close(fd);
	unlink(path);
	assert(splash_logo_needs_capture(path, "BUILD_ID=\"a\""));      /* no stamp */
	FILE *f = fopen(path, "w");
	fputs("BUILD_ID=\"a\"\n", f);
	fclose(f);
	assert(!splash_logo_needs_capture(path, "BUILD_ID=\"a\""));     /* same build */
	assert(splash_logo_needs_capture(path, "BUILD_ID=\"b\""));      /* new build */
	unlink(path);
}


static void test_boot_seconds(void)
{
	char path[] = "/tmp/splash-secs-XXXXXX";
	int fd = mkstemp(path);
	close(fd);
	unlink(path);
	assert(splash_read_seconds(path) == 0);          /* missing: unknown */
	assert(splash_write_seconds(path, 21.5) == 0);
	assert(splash_read_seconds(path) == 21.5);
	FILE *f = fopen(path, "w");
	fputs("garbage\n", f);
	fclose(f);
	assert(splash_read_seconds(path) == 0);          /* unreadable: unknown */
	f = fopen(path, "w");
	fputs("500\n", f);
	fclose(f);
	assert(splash_read_seconds(path) == 0);          /* out of range: unknown */
	unlink(path);
}

static void test_synced_writes(void)
{
	char path[] = "/tmp/splash-sync-XXXXXX";
	int fd = mkstemp(path);
	FILE *f = fdopen(fd, "w");
	fputs("logo", f);
	assert(splash_close_synced(f) == 0);
	f = fopen(path, "r");
	char buf[8] = "";
	assert(fgets(buf, sizeof(buf), f) && strcmp(buf, "logo") == 0);
	fclose(f);
	assert(splash_sync_dir(path) == 0);
	assert(splash_sync_dir("/nonexistent-a12/logo.bmp") != 0);
	unlink(path);
}

static void test_cmdline_token(void)
{
	char path[] = "/tmp/splash-cmdline-XXXXXX";
	int fd = mkstemp(path);
	FILE *f = fdopen(fd, "w");
	fputs("console=tty0 a12_kms_splash quiet panel_a12.refresh_60hz=1\n", f);
	fclose(f);
	assert(splash_cmdline_has(path, "a12_kms_splash"));
	assert(splash_cmdline_has(path, "quiet") && splash_cmdline_has(path, "console=tty0"));
	assert(!splash_cmdline_has(path, "a12_kms"));		/* whole tokens only */
	assert(!splash_cmdline_has(path, "splash"));
	f = fopen(path, "w");
	fputs("no_a12_kms_splash a12_kms_splash_off\n", f);
	fclose(f);
	assert(!splash_cmdline_has(path, "a12_kms_splash"));
	unlink(path);
	assert(!splash_cmdline_has("/nonexistent-cmdline", "a12_kms_splash"));
}

int main(void)
{
	test_rejects_unsupported_fb();
	test_logo_capture_stamp();
	test_boot_seconds();
	test_synced_writes();
	test_cmdline_token();
	puts("splash main: ok");
	return 0;
}
