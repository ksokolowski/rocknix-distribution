// SPDX-License-Identifier: GPL-2.0-or-later
// A12 splash state: boot progress, current unit text and when to exit.
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "splash-progress.h"

static const char *const shown[] = { ".service", ".mount", ".socket", ".timer", ".path" };

void splash_state_init(struct splash_state *s, double now)
{
	memset(s, 0, sizeof(*s));
	s->started_at = now;
	s->timeout = SPLASH_TIMEOUT_S;
}

void splash_state_first_boot(struct splash_state *s)
{
	s->timeout = SPLASH_FIRST_BOOT_TIMEOUT_S;
}

void splash_on_progress(struct splash_state *s, double progress)
{
	s->progress = progress < 0 ? 0 : progress > 1 ? 1 : progress;
}

int splash_unit_shown(const char *unit)
{
	const char *dot = strrchr(unit, '.');
	for (size_t i = 0; dot && i < sizeof(shown) / sizeof(shown[0]); i++)
		if (strcmp(dot, shown[i]) == 0)
			return 1;
	return 0;
}

/* "<verb> <description>", as systemd's console shows it, or without one
 * "<verb> <name>": unit name without type and instance, '-'/'_' as spaces. */
static int unit_label(const char *unit, const char *description, const char *verb, char *out, size_t size)
{
	const char *dot = strrchr(unit, '.');
	if (!splash_unit_shown(unit))
		return 0;
	if (description && description[0]) {
		snprintf(out, size, "%s %s", verb, description);
		return 1;
	}
	char name[80];
	size_t n = (size_t)(dot - unit);
	const char *at = memchr(unit, '@', n);
	if (at)
		n = (size_t)(at - unit);
	if (n >= sizeof(name))
		n = sizeof(name) - 1;
	memcpy(name, unit, n);
	name[n] = 0;
	for (char *p = name; *p; p++)
		if (*p == '-' || *p == '_')
			*p = ' ';
	snprintf(out, size, "%s %s", verb, name);
	return 1;
}

void splash_on_job_new(struct splash_state *s, const char *unit, const char *description)
{
	unit_label(unit, description, "Starting", s->text, sizeof(s->text));
}

void splash_stop_init(struct splash_stop *s)
{
	memset(s, 0, sizeof(*s));
	snprintf(s->text, sizeof(s->text), "Shutting down...");
}

void splash_stop_update(struct splash_stop *s, int stop_jobs, const char *running_unit,
			const char *description)
{
	/* systemd queues the whole shutdown transaction at once, so the largest
	 * count seen is the total and the remaining count only goes down. */
	if (stop_jobs > s->total)
		s->total = stop_jobs;
	if (stop_jobs > 0)
		s->seen = 1;
	s->remaining = stop_jobs;
	if (!running_unit || !unit_label(running_unit, description, "Stopping", s->text, sizeof(s->text)))
		if (stop_jobs == 0)
			snprintf(s->text, sizeof(s->text), "Shutting down...");
}

double splash_stop_fraction(const struct splash_stop *s)
{
	return s->total > 0 ? (double)s->remaining / s->total : 1.0;
}

int splash_stop_done(const struct splash_stop *s)
{
	return s->seen && s->remaining == 0;
}

void splash_on_job_removed(struct splash_state *s, const char *unit, const char *result)
{
	if (strcmp(unit, "emustation.service") == 0 && strcmp(result, "done") == 0)
		s->done = 1;
}

int splash_should_exit(const struct splash_state *s, double now)
{
	return s->done || now - s->started_at >= s->timeout;
}

double splash_display(struct splash_state *s, double now, double last_boot_s)
{
	double f = s->progress;
	if (last_boot_s > 0) {
		f = (now - s->started_at) / last_boot_s;
		if (f > 1)
			f = 1;
	}
	f *= SPLASH_HANDOVER;
	if (f > s->shown)
		s->shown = f;
	return s->shown;
}

int splash_bus_lost(int r)
{
	return r < 0 && r != -EINTR;
}
