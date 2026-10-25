// SPDX-License-Identifier: GPL-2.0-or-later
// Run a12-splash's systemd loops (splash-sd.c) against scripted sd-bus replies.
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <systemd/sd-bus.h>
#include "../packages/a12-controls/sources/splash/splash-draw.h"
#include "../packages/a12-controls/sources/splash/splash-fb.h"
#include "../packages/a12-controls/sources/splash/splash-sd.h"

struct job { const char *unit, *type, *state; };
struct sd_bus { int open; };
struct sd_bus_message { const struct job *jobs; int n, i; };
static int descriptions;	/* Description property reads */

/* Scripted ListJobs replies; NULL jobs with n < 0 means the bus fails. */
struct step { const struct job *jobs; int n; };
static const struct step *steps;
static int nsteps, step_at, connects, fail_connects, es_active, process_fail_at = -1, processes;

int sd_bus_new(sd_bus **ret) { *ret = calloc(1, sizeof(sd_bus)); return 0; }
int sd_bus_set_address(sd_bus *bus, const char *address) { (void)bus; (void)address; return 0; }
int sd_bus_start(sd_bus *bus)
{
	connects++;
	if (fail_connects > 0) { fail_connects--; return -ENOENT; }
	bus->open = 1;
	return 0;
}
sd_bus *sd_bus_unref(sd_bus *bus) { free(bus); return NULL; }
sd_bus *sd_bus_flush_close_unref(sd_bus *bus) { free(bus); return NULL; }
int sd_bus_process(sd_bus *bus, sd_bus_message **r)
{
	(void)bus; (void)r;
	return processes++ == process_fail_at ? -ECONNRESET : 0;
}
int sd_bus_wait(sd_bus *bus, uint64_t usec) { (void)bus; (void)usec; usleep(20000); return 0; }
int sd_bus_match_signal(sd_bus *bus, sd_bus_slot **ret, const char *sender, const char *path, const char *interface,
			const char *member, sd_bus_message_handler_t callback, void *userdata)
{
	(void)bus; (void)ret; (void)sender; (void)path; (void)interface; (void)member; (void)callback; (void)userdata;
	return 0;
}
int sd_bus_call_method(sd_bus *bus, const char *destination, const char *path, const char *interface,
		       const char *member, sd_bus_error *ret_error, sd_bus_message **reply, const char *types, ...)
{
	(void)bus; (void)destination; (void)path; (void)interface; (void)ret_error; (void)types;
	if (strcmp(member, "ListJobs") != 0 || !reply)
		return 0;
	const struct step *s = &steps[step_at < nsteps ? step_at : nsteps - 1];
	step_at++;
	if (s->n < 0)
		return -ECONNRESET;
	*reply = calloc(1, sizeof(sd_bus_message));
	(*reply)->jobs = s->jobs;
	(*reply)->n = s->n;
	return 1;
}
int sd_bus_get_property_trivial(sd_bus *bus, const char *destination, const char *path, const char *interface,
				const char *member, sd_bus_error *ret_error, char type, void *ret_ptr)
{
	(void)bus; (void)destination; (void)path; (void)interface; (void)member; (void)ret_error; (void)type;
	*(double *)ret_ptr = 0.5;
	return 0;
}
int sd_bus_get_property_string(sd_bus *bus, const char *destination, const char *path, const char *interface,
			       const char *member, sd_bus_error *ret_error, char **ret)
{
	(void)bus; (void)destination; (void)interface; (void)ret_error;
	if (strcmp(member, "Description") == 0) {
		assert(strcmp(path, "/unit") == 0);	/* the unit path ListJobs gave */
		descriptions++;
		*ret = strdup("Fixture unit");
		return 0;
	}
	assert(strstr(path, "emustation_2eservice"));
	*ret = strdup(es_active ? "active" : "activating");
	return 0;
}
int sd_bus_message_enter_container(sd_bus_message *m, char type, const char *contents)
{
	(void)m; (void)type; (void)contents;
	return 1;
}
int sd_bus_message_read(sd_bus_message *m, const char *types, ...)
{
	va_list ap;
	if (strcmp(types, "(usssoo)") != 0 || m->i >= m->n)
		return 0;
	const struct job *j = &m->jobs[m->i++];
	va_start(ap, types);
	*va_arg(ap, uint32_t *) = (uint32_t)m->i;
	*va_arg(ap, const char **) = j->unit;
	*va_arg(ap, const char **) = j->type;
	*va_arg(ap, const char **) = j->state;
	*va_arg(ap, const char **) = "/job";
	*va_arg(ap, const char **) = "/unit";
	va_end(ap);
	return 1;
}
sd_bus_message *sd_bus_message_unref(sd_bus_message *m) { free(m); return NULL; }

static uint32_t pixels[1024 * 600];
static struct splash_frame frame = { pixels, 1024, 600, 1024 };
static struct splash_layout layout;

static int bar_filled(void)
{
	int n = 0;
	for (int i = 0; i < layout.bar_w; i++)
		if ((pixels[(layout.bar_y + 1) * 1024 + layout.bar_x + i] & 0xFF0000) >= 0x4F0000 &&
		    (pixels[(layout.bar_y + 1) * 1024 + layout.bar_x + i] & 0x00FF00) <= 0x101000)
			n++;
	return n;
}

static void test_stopping_runs_down_and_ends(void)
{
	static const struct job three[] = { { "emustation.service", "stop", "running" },
					    { "sshd.service", "stop", "waiting" },
					    { "storage.mount", "stop", "waiting" },
					    { "poweroff.target", "start", "waiting" } };
	static const struct job one[] = { { "storage.mount", "stop", "running" } };
	static const struct step script[] = { { three, 4 }, { three + 1, 3 }, { one, 1 }, { NULL, 0 } };
	steps = script; nsteps = 4; step_at = 0; connects = 0; fail_connects = 0;
	descriptions = 0;
	assert(splash_sd_stopping(&frame, &layout) == 0);
	assert(step_at == 4);		/* stopped polling once no stop job remained */
	assert(descriptions > 0);	/* the running unit is labelled by its Description */
	assert(bar_filled() == 0);	/* ends with an empty bar */
}

static void test_stopping_ends_when_bus_goes(void)
{
	static const struct job two[] = { { "a.service", "stop", "running" }, { "b.service", "stop", "waiting" } };
	static const struct step script[] = { { two, 2 }, { NULL, -1 } };
	steps = script; nsteps = 2; step_at = 0;
	assert(splash_sd_stopping(&frame, &layout) == 0);
	assert(step_at == 2);
}

static void test_boot_survives_bus_loss(void)
{
	static const struct job none[] = { { "x.service", "start", "waiting" } };
	static const struct step script[] = { { none, 1 } };
	char seconds[] = "/tmp/splash-sd-secs-XXXXXX";
	int fd = mkstemp(seconds);
	close(fd);
	unlink(seconds);
	steps = script; nsteps = 1; step_at = 0; connects = 0;
	/* The bus drops on the third process() call; the reconnect a second
	 * later finds ES already active, so the loop ends long before 90 s. */
	processes = 0; process_fail_at = 2; fail_connects = 0; es_active = 1;
	assert(splash_sd_run(&frame, &layout, seconds, 1, 0) == 0);
	assert(connects == 2);
	assert(splash_read_seconds(seconds) > 0);	/* recorded: 1-2 s */
	/* First boot of a build (record = 0): boot-seconds stays as it was. */
	FILE *f = fopen(seconds, "w");
	fputs("42.0\n", f);
	fclose(f);
	processes = 0; process_fail_at = 2; connects = 0;
	assert(splash_sd_run(&frame, &layout, seconds, 0, 0) == 0);
	assert(splash_read_seconds(seconds) == 42.0);
	/* A card's first boot is minutes of copying: it must not pace the next
	 * boot even when the build is known (record = 1). */
	processes = 0; process_fail_at = 2; connects = 0;
	assert(splash_sd_run(&frame, &layout, seconds, 1, 1) == 0);
	assert(splash_read_seconds(seconds) == 42.0);
	unlink(seconds);
}

int main(void)
{
	splash_layout_for(1024, 600, &layout);
	test_stopping_runs_down_and_ends();
	test_stopping_ends_when_bus_goes();
	test_boot_survives_bus_loss();
	puts("splash sd: ok");
	return 0;
}
