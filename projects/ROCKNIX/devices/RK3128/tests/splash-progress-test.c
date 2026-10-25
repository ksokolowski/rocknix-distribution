// SPDX-License-Identifier: GPL-2.0-or-later
// Host test for A12 splash progress state (Task 3 of the boot splash plan).
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "../packages/a12-controls/sources/splash/splash-progress.h"

static void test_names(void)
{
	struct splash_state s;
	splash_state_init(&s, 0);
	splash_on_job_new(&s, "NetworkManager.service", NULL);
	assert(strcmp(s.text, "Starting NetworkManager") == 0);
	splash_on_job_new(&s, "systemd-hwdb-update.service", NULL);
	assert(strcmp(s.text, "Starting systemd hwdb update") == 0);
	splash_on_job_new(&s, "getty@tty1.service", NULL);
	assert(strcmp(s.text, "Starting getty") == 0);
	splash_on_job_new(&s, "basic.target", NULL);          /* ignored */
	assert(strcmp(s.text, "Starting getty") == 0);
	splash_on_job_new(&s, "dev-mmcblk0p2.device", NULL);  /* ignored */
	assert(strcmp(s.text, "Starting getty") == 0);
	splash_on_job_new(&s, "storage.mount", NULL);
	assert(strcmp(s.text, "Starting storage") == 0);
}

/* The unit's Description wins over its name, as on systemd's console; an
 * empty one falls back to the name. Kinds that are not shown stay hidden. */
static void test_descriptions(void)
{
	struct splash_state s;
	splash_state_init(&s, 0);
	splash_on_job_new(&s, "a12-diagnostics.service", "Hardware diagnostics");
	assert(strcmp(s.text, "Starting Hardware diagnostics") == 0);
	splash_on_job_new(&s, "NetworkManager.service", "");
	assert(strcmp(s.text, "Starting NetworkManager") == 0);
	splash_on_job_new(&s, "basic.target", "Basic System");	/* ignored */
	assert(strcmp(s.text, "Starting NetworkManager") == 0);
	struct splash_stop t;
	splash_stop_init(&t);
	splash_stop_update(&t, 3, "a12-irq-affinity.service", "Interrupt balancing");
	assert(strcmp(t.text, "Stopping Interrupt balancing") == 0);
	splash_stop_update(&t, 2, "sshd.service", NULL);
	assert(strcmp(t.text, "Stopping sshd") == 0);
}

static void test_progress_and_exit(void)
{
	struct splash_state s;
	splash_state_init(&s, 10.0);
	splash_on_progress(&s, 0.4);
	assert(s.progress == 0.4);
	splash_on_progress(&s, 1.7);
	assert(s.progress == 1.0);
	assert(!splash_should_exit(&s, 20.0));
	splash_on_job_removed(&s, "emustation.service", "failed");
	assert(!splash_should_exit(&s, 20.0));
	splash_on_job_removed(&s, "emustation.service", "done");
	assert(splash_should_exit(&s, 20.0));
}

static void test_timeout(void)
{
	struct splash_state s;
	splash_state_init(&s, 100.0);
	assert(!splash_should_exit(&s, 100.0 + SPLASH_TIMEOUT_S - 1));
	assert(splash_should_exit(&s, 100.0 + SPLASH_TIMEOUT_S));
}

/* sync11's first boot: userconfig copied /usr/config for 3.5 min and the
 * splash had left at 90 s, so the logo stood alone for minutes. */
static void test_first_boot_timeout(void)
{
	struct splash_state s;
	splash_state_init(&s, 100.0);
	splash_state_first_boot(&s);
	assert(!splash_should_exit(&s, 100.0 + SPLASH_TIMEOUT_S));
	assert(!splash_should_exit(&s, 100.0 + SPLASH_FIRST_BOOT_TIMEOUT_S - 1));
	assert(splash_should_exit(&s, 100.0 + SPLASH_FIRST_BOOT_TIMEOUT_S));
	splash_on_job_removed(&s, "emustation.service", "done");
	assert(splash_should_exit(&s, 101.0));		/* ES still ends it */
}


static void test_display_monotonic(void)
{
	struct splash_state s;
	splash_state_init(&s, 0);
	splash_on_progress(&s, 0.9);
	double a = splash_display(&s, 1.0, 0);
	assert(a > 0.89 && a < 0.91);            /* systemd's 0.9 */
	splash_on_progress(&s, 0.5);             /* systemd queued more jobs */
	assert(splash_display(&s, 2.0, 0) == a); /* never moves backwards */
}

static void test_display_paced_by_last_boot(void)
{
	struct splash_state s;
	splash_state_init(&s, 10.0);
	splash_on_progress(&s, 0.95);            /* systemd races ahead early */
	double d = splash_display(&s, 15.0, 20.0);
	assert(d > 0.24 && d < 0.26);            /* 5 of 20 s */
	assert(splash_display(&s, 60.0, 20.0) == SPLASH_HANDOVER);
	/* ES draws its own themed splash, so a12-splash ends with a full bar. */
	assert(SPLASH_HANDOVER == 1.0);
}


static void test_unit_shown(void)
{
	assert(splash_unit_shown("NetworkManager.service"));
	assert(splash_unit_shown("storage.mount"));
	assert(!splash_unit_shown("basic.target"));
	assert(!splash_unit_shown("dev-mmcblk0p2.device"));
	assert(!splash_unit_shown("noextension"));
}

static void test_bus_lost(void)
{
	assert(!splash_bus_lost(0));
	assert(!splash_bus_lost(1));
	assert(!splash_bus_lost(-EINTR));
	assert(splash_bus_lost(-ECONNRESET));
	assert(splash_bus_lost(-ENOTCONN));
}

static void test_stop_progress(void)
{
	struct splash_stop s;
	splash_stop_init(&s);
	assert(strcmp(s.text, "Shutting down...") == 0);
	assert(splash_stop_fraction(&s) == 1.0 && !splash_stop_done(&s));
	splash_stop_update(&s, 4, "emustation.service", NULL);
	assert(strcmp(s.text, "Stopping emustation") == 0);
	assert(splash_stop_fraction(&s) == 1.0);
	splash_stop_update(&s, 2, "systemd-timesyncd.service", NULL);
	assert(strcmp(s.text, "Stopping systemd timesyncd") == 0);
	assert(splash_stop_fraction(&s) == 0.5);
	splash_stop_update(&s, 1, "dev-zram0.swap", NULL);	/* not shown: keep the last label */
	assert(strcmp(s.text, "Stopping systemd timesyncd") == 0);
	assert(splash_stop_fraction(&s) == 0.25 && !splash_stop_done(&s));
	splash_stop_update(&s, 0, NULL, NULL);
	assert(splash_stop_done(&s) && splash_stop_fraction(&s) == 0.0);
	assert(strcmp(s.text, "Shutting down...") == 0);
	/* Nothing queued yet (started before the transaction is visible). */
	splash_stop_init(&s);
	splash_stop_update(&s, 0, NULL, NULL);
	assert(!splash_stop_done(&s));
}

int main(void)
{
	test_descriptions();
	test_names();
	test_unit_shown();
	test_progress_and_exit();
	test_timeout();
	test_first_boot_timeout();
	test_display_monotonic();
	test_display_paced_by_last_boot();
	test_bus_lost();
	test_stop_progress();
	puts("splash progress: ok");
	return 0;
}
