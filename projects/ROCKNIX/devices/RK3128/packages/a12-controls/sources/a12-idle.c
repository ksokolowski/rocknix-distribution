// SPDX-License-Identifier: GPL-2.0-or-later
// Idle mode: the screen goes dark after a time without input; the press that
// wakes it is swallowed with every event until all keys are released.
#include <stdlib.h>
#include <string.h>
#include "a12-idle.h"

#define IDLE_ES_DEFAULT_MS 300000
#define IDLE_GAME_MS 900000

void idle_init(struct idle_state *s, long long now_ms)
{
    memset(s, 0, sizeof(*s));
    s->last_input_ms = now_ms;
    for (int i = 0; i < ABS_CNT; i++) {
        s->min[i] = -32768;
        s->max[i] = 32767;
    }
}

int idle_timeout_ms(bool in_game, const char *es_screensaver_ms)
{
    if (in_game)
        return IDLE_GAME_MS;
    if (!es_screensaver_ms)
        return IDLE_ES_DEFAULT_MS;
    char *end;
    long value = strtol(es_screensaver_ms, &end, 10);
    if (end == es_screensaver_ms || *end || value <= 0)
        return 0;
    return (int)value;
}

void idle_set_axis_range(struct idle_state *s, unsigned code, int min, int max)
{
    if (code < ABS_CNT && max > min) {
        s->min[code] = min;
        s->max[code] = max;
    }
}

// An axis counts as input only when it moves beyond 1/8 of its range from
// where it rests, so stick jitter neither keeps the screen awake nor wakes it.
static bool axis_moved(struct idle_state *s, unsigned code, int value)
{
    if (code >= ABS_CNT)
        return false;
    if (!s->has_ref[code]) {
        s->has_ref[code] = true;
        s->ref[code] = value;
        return false;
    }
    if (abs(value - s->ref[code]) * 8 <= s->max[code] - s->min[code])
        return false;
    s->ref[code] = value;
    return true;
}

bool idle_on_event(struct idle_state *s, const struct input_event *ev, long long now_ms, enum idle_action *action)
{
    bool input = false;
    *action = IDLE_NONE;
    if (ev->type == EV_KEY) {
        if (ev->value == 1)
            s->held++;
        else if (ev->value == 0 && s->held > 0)
            s->held--;
        input = true;
    } else if (ev->type == EV_ABS) {
        input = axis_moved(s, ev->code, ev->value);
    }
    if (input)
        s->last_input_ms = now_ms;
    if (s->dark) {
        if (input && (ev->type == EV_ABS || ev->value == 1)) {
            s->dark = false;
            s->swallowing = s->held > 0;
            *action = IDLE_WAKE;
        }
        return true;
    }
    if (s->swallowing) {
        if (s->held == 0 && ev->type == EV_KEY)
            s->swallowing = false;
        return true;
    }
    return false;
}

// The kernel reports no key down: a release may have been lost.
void idle_keys_released(struct idle_state *s)
{
    s->held = 0;
    s->swallowing = false;
}

enum idle_action idle_on_tick(struct idle_state *s, long long now_ms, int timeout_ms)
{
    if (timeout_ms <= 0 || s->dark || s->swallowing)
        return IDLE_NONE;
    if (now_ms - s->last_input_ms < timeout_ms)
        return IDLE_NONE;
    s->dark = true;
    return IDLE_DARKEN;
}

bool idle_is_dark(const struct idle_state *s)
{
    return s->dark;
}
