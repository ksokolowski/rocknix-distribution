/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SPLASH_PROGRESS_H
#define SPLASH_PROGRESS_H
#define SPLASH_TIMEOUT_S 90.0
/* A card's first boot copies the default configuration for minutes. */
#define SPLASH_FIRST_BOOT_TIMEOUT_S 900.0
/* Bar level reached when ES starts; ES then shows its own themed splash. */
#define SPLASH_HANDOVER 1.0
struct splash_state { double progress; char text[96]; int done; double started_at; double shown; double timeout; };
void splash_state_init(struct splash_state *s, double now);
/* Stay until ES (at most SPLASH_FIRST_BOOT_TIMEOUT_S) instead of the usual limit. */
void splash_state_first_boot(struct splash_state *s);
void splash_on_progress(struct splash_state *s, double progress);
/* 1 if the unit kind is shown as "Starting <name>" (services, mounts, ...). */
int splash_unit_shown(const char *unit);
/* description: the unit's Description (shown when not empty) or NULL; the
 * label falls back to the unit name. */
void splash_on_job_new(struct splash_state *s, const char *unit, const char *description);
void splash_on_job_removed(struct splash_state *s, const char *unit, const char *result);
int splash_should_exit(const struct splash_state *s, double now);
/* Bar fraction to draw: paced by the previous boot's duration when known
 * (last_boot_s > 0), else systemd's progress; scaled to SPLASH_HANDOVER and
 * never decreasing (systemd's fraction drops when jobs are queued). */
double splash_display(struct splash_state *s, double now, double last_boot_s);
/* Shutdown: stop jobs remaining out of the largest count seen. */
struct splash_stop { int total, remaining, seen; char text[96]; };
void splash_stop_init(struct splash_stop *s);
/* stop_jobs: stop jobs queued now; running_unit: one being stopped or NULL,
 * with its Description or NULL. */
void splash_stop_update(struct splash_stop *s, int stop_jobs, const char *running_unit,
			const char *description);
/* Bar fraction for the shutdown bar, which runs down from full. */
double splash_stop_fraction(const struct splash_stop *s);
/* 1 once stop jobs were seen and none remain. */
int splash_stop_done(const struct splash_stop *s);
/* 1 if an sd-bus call result means the connection is gone (not -EINTR). */
int splash_bus_lost(int r);
/* Seconds between reconnect attempts after the bus was lost. */
#define SPLASH_RECONNECT_S 1.0
#endif
