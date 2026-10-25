// SPDX-License-Identifier: GPL-2.0-or-later
// Follow systemd jobs over its private socket and draw progress (boot mode).
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <systemd/sd-bus.h>
#include "splash-fb.h"
#include "splash-progress.h"
#include "splash-sd.h"

#define MANAGER "org.freedesktop.systemd1.Manager"

static double now_s(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec / 1e9;
}

/* The unit's Description, as systemd's console shows it, or "". */
static void unit_description(sd_bus *bus, const char *unit_path, char *out, size_t size)
{
	char *d = NULL;
	out[0] = 0;
	if (sd_bus_get_property_string(bus, "org.freedesktop.systemd1", unit_path,
				       "org.freedesktop.systemd1.Unit", "Description", NULL, &d) >= 0 && d)
		snprintf(out, size, "%s", d);
	free(d);
}

/* JobNew fires when a job is queued, mostly before a12-splash connects;
 * show the first start job systemd is actually running instead. */
static void show_running_job(sd_bus *bus, struct splash_state *s)
{
	sd_bus_message *reply = NULL;
	uint32_t id;
	const char *unit, *type, *state, *job, *unit_path;

	if (sd_bus_call_method(bus, "org.freedesktop.systemd1", "/org/freedesktop/systemd1", MANAGER,
			       "ListJobs", NULL, &reply, "") < 0)
		return;
	if (sd_bus_message_enter_container(reply, 'a', "(usssoo)") >= 0) {
		while (sd_bus_message_read(reply, "(usssoo)", &id, &unit, &type, &state, &job, &unit_path) > 0) {
			if (strcmp(type, "start") == 0 && strcmp(state, "running") == 0 &&
			    splash_unit_shown(unit)) {
				char description[96];
				unit_description(bus, unit_path, description, sizeof(description));
				splash_on_job_new(s, unit, description);
				break;
			}
		}
	}
	sd_bus_message_unref(reply);
}

static int on_job_removed(sd_bus_message *m, void *data, sd_bus_error *err)
{
	uint32_t id; const char *path, *unit, *result;
	(void)err;
	if (sd_bus_message_read(m, "uoss", &id, &path, &unit, &result) >= 0)
		splash_on_job_removed(data, unit, result);
	return 0;
}

static sd_bus *connect_once(void)
{
	sd_bus *bus = NULL;
	if (sd_bus_new(&bus) >= 0 &&
	    sd_bus_set_address(bus, "unix:path=/run/systemd/private") >= 0 &&
	    sd_bus_start(bus) >= 0)
		return bus;
	sd_bus_unref(bus);
	return NULL;
}

static sd_bus *connect_private(void)
{
	for (int attempt = 0; attempt < 50; attempt++) {
		sd_bus *bus = connect_once();
		if (bus)
			return bus;
		usleep(100000);
	}
	return NULL;
}

static void subscribe(sd_bus *bus, struct splash_state *s)
{
	sd_bus_match_signal(bus, NULL, NULL, "/org/freedesktop/systemd1", MANAGER, "JobRemoved", on_job_removed, s);
	sd_bus_call_method(bus, "org.freedesktop.systemd1", "/org/freedesktop/systemd1", MANAGER,
			   "Subscribe", NULL, NULL, "");
}

/* After a reconnect the JobRemoved for ES may have been missed. */
static void check_es_active(sd_bus *bus, struct splash_state *s)
{
	char *state = NULL;
	if (sd_bus_get_property_string(bus, "org.freedesktop.systemd1",
				       "/org/freedesktop/systemd1/unit/emustation_2eservice",
				       "org.freedesktop.systemd1.Unit", "ActiveState", NULL, &state) >= 0 &&
	    strcmp(state, "active") == 0)
		splash_on_job_removed(s, "emustation.service", "done");
	free(state);
}

int splash_sd_run(struct splash_frame *f, const struct splash_layout *l, const char *seconds_path, int record,
		  int first_boot)
{
	struct splash_state s;
	char shown_text[96] = "";
	double last = -1;
	double last_boot = splash_read_seconds(seconds_path);
	splash_state_init(&s, now_s());
	if (first_boot) {
		splash_state_first_boot(&s);
		record = 0;
	}
	splash_bar(f, l, 0);
	double retry_at = 0;
	sd_bus *bus = connect_private();
	if (bus)
		subscribe(bus, &s);
	while (!splash_should_exit(&s, now_s())) {
		if (bus) {
			double p = 0;
			int r;
			while ((r = sd_bus_process(bus, NULL)) > 0)
				;
			if (!splash_bus_lost(r)) {
				if (sd_bus_get_property_trivial(bus, "org.freedesktop.systemd1", "/org/freedesktop/systemd1",
								MANAGER, "Progress", NULL, 'd', &p) >= 0)
					splash_on_progress(&s, p);
				show_running_job(bus, &s);
				r = sd_bus_wait(bus, 250000);
			}
			/* A dropped bus makes process and wait return at once:
			 * close it and retry at a slow pace instead of spinning. */
			if (splash_bus_lost(r)) {
				bus = sd_bus_flush_close_unref(bus);
				retry_at = now_s() + SPLASH_RECONNECT_S;
			}
		} else {
			usleep(250000);
			if (retry_at > 0 && now_s() >= retry_at) {
				bus = connect_once();
				if (bus) {
					subscribe(bus, &s);
					check_es_active(bus, &s);
				} else {
					retry_at = now_s() + SPLASH_RECONNECT_S;
				}
			}
		}
		double shown = splash_display(&s, now_s(), last_boot);
		if (shown - last > 0.002) {
			splash_bar(f, l, shown);
			last = shown;
		}
		if (strcmp(shown_text, s.text) != 0) {
			splash_text(f, l, s.text);
			memcpy(shown_text, s.text, sizeof(shown_text));
		}
	}
	sd_bus_flush_close_unref(bus);
	/* Show the finished bar briefly, then leave only the logo on fbdev,
	 * which is what shows whenever ES releases the display. */
	if (s.done) {
		splash_bar(f, l, 1.0);
		usleep(200000);
	}
	splash_clear_progress(f, l);
	if (s.done && record)
		splash_write_seconds(seconds_path, now_s() - s.started_at);
	return 0;
}

/* Number of queued stop jobs (-1 if the bus failed); running gets the first
 * shown unit whose stop job is running, or "", and description its
 * Description. */
static int count_stop_jobs(sd_bus *bus, char *running, size_t size, char *description, size_t dsize)
{
	sd_bus_message *reply = NULL;
	uint32_t id;
	const char *unit, *type, *state, *job, *unit_path;
	int count = 0;

	running[0] = 0;
	description[0] = 0;
	if (sd_bus_call_method(bus, "org.freedesktop.systemd1", "/org/freedesktop/systemd1", MANAGER,
			       "ListJobs", NULL, &reply, "") < 0)
		return -1;
	if (sd_bus_message_enter_container(reply, 'a', "(usssoo)") >= 0) {
		while (sd_bus_message_read(reply, "(usssoo)", &id, &unit, &type, &state, &job, &unit_path) > 0) {
			if (strcmp(type, "stop") != 0)
				continue;
			count++;
			if (!running[0] && strcmp(state, "running") == 0 && splash_unit_shown(unit)) {
				snprintf(running, size, "%s", unit);
				unit_description(bus, unit_path, description, dsize);
			}
		}
	}
	sd_bus_message_unref(reply);
	return count;
}

int splash_sd_stopping(struct splash_frame *f, const struct splash_layout *l)
{
	struct splash_stop s;
	char shown_text[96] = "";
	double last = -1;
	double started = now_s();

	splash_stop_init(&s);
	splash_bar(f, l, 1.0);
	sd_bus *bus = connect_private();
	while (bus && now_s() - started < SPLASH_TIMEOUT_S) {
		char running[128], description[96];
		int n = count_stop_jobs(bus, running, sizeof(running), description, sizeof(description));
		if (n < 0)
			break;	/* systemd has moved on to the final stage */
		splash_stop_update(&s, n, running[0] ? running : NULL, description);
		double shown = splash_stop_fraction(&s);
		if (shown > last + 0.002 || shown < last - 0.002) {
			splash_bar(f, l, shown);
			last = shown;
		}
		if (strcmp(shown_text, s.text) != 0) {
			splash_text(f, l, s.text);
			memcpy(shown_text, s.text, sizeof(shown_text));
		}
		if (splash_stop_done(&s))
			break;
		usleep(100000);
	}
	sd_bus_flush_close_unref(bus);
	splash_bar(f, l, 0);
	splash_text(f, l, "Shutting down...");
	return 0;
}
