// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef A12_IDLE_H
#define A12_IDLE_H
#include <linux/input.h>
#include <stdbool.h>

enum idle_action { IDLE_NONE, IDLE_DARKEN, IDLE_WAKE };

struct idle_state {
    long long last_input_ms;
    bool dark;
    bool swallowing;
    int held;
    bool has_ref[ABS_CNT];
    int ref[ABS_CNT];
    int min[ABS_CNT];
    int max[ABS_CNT];
};

void idle_init(struct idle_state *s, long long now_ms);
int idle_timeout_ms(bool in_game, const char *es_screensaver_ms);
bool idle_on_event(struct idle_state *s, const struct input_event *ev, long long now_ms, enum idle_action *action);
enum idle_action idle_on_tick(struct idle_state *s, long long now_ms, int timeout_ms);
bool idle_is_dark(const struct idle_state *s);
void idle_keys_released(struct idle_state *s);
void idle_set_axis_range(struct idle_state *s, unsigned code, int min, int max);
#endif
