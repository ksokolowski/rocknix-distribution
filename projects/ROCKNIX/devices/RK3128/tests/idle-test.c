// SPDX-License-Identifier: GPL-2.0-or-later
// Idle mode of the A12 input daemon (power policy, 2026-10-26): the screen
// goes dark after the idle time, and the press that wakes it is swallowed
// with every event until all keys are released.
#include <assert.h>
#include <stdio.h>
#include "../packages/a12-controls/sources/a12-idle.c"

static struct idle_state s;
static enum idle_action action;

static bool key(long long now, unsigned short code, int value)
{
    struct input_event ev = { .type = EV_KEY, .code = code, .value = value };
    return idle_on_event(&s, &ev, now, &action);
}

static bool axis(long long now, unsigned short code, int value)
{
    struct input_event ev = { .type = EV_ABS, .code = code, .value = value };
    return idle_on_event(&s, &ev, now, &action);
}

static void darken(long long now)
{
    idle_init(&s, now);
    assert(idle_on_tick(&s, now + 300000, 300000) == IDLE_DARKEN && idle_is_dark(&s));
}

int main(void)
{
    assert(idle_timeout_ms(true, "60000") == 900000);
    assert(idle_timeout_ms(false, NULL) == 300000);
    assert(idle_timeout_ms(false, "120000") == 120000);
    assert(idle_timeout_ms(false, "0") == 0);
    assert(idle_timeout_ms(false, "x") == 0);

    idle_init(&s, 0);
    assert(idle_on_tick(&s, 299999, 300000) == IDLE_NONE);
    assert(idle_on_tick(&s, 300000, 300000) == IDLE_DARKEN);
    assert(idle_on_tick(&s, 300001, 300000) == IDLE_NONE && idle_is_dark(&s));

    // Input before the timeout restarts it.
    idle_init(&s, 0);
    assert(!key(200000, BTN_A, 1) && action == IDLE_NONE);
    assert(!key(200050, BTN_A, 0));
    assert(idle_on_tick(&s, 400000, 300000) == IDLE_NONE);
    assert(idle_on_tick(&s, 500050, 300000) == IDLE_DARKEN);

    // A hotkey that wakes the screen does nothing else: press and release
    // are both swallowed; the next press is normal.
    darken(0);
    assert(key(400000, KEY_VOLUMEUP, 1) && action == IDLE_WAKE && !idle_is_dark(&s));
    assert(key(400100, KEY_VOLUMEUP, 0) && action == IDLE_NONE);
    assert(!key(400200, BTN_A, 1));
    assert(!key(400300, BTN_A, 0));

    // The exit chord used to wake: swallowed until both keys are up.
    darken(0);
    assert(key(400000, BTN_SELECT, 1) && action == IDLE_WAKE);
    assert(key(400010, BTN_START, 1) && action == IDLE_NONE);
    assert(key(400020, BTN_START, 2));
    assert(key(400030, BTN_START, 0));
    assert(key(400040, BTN_SELECT, 0));
    assert(!key(400050, BTN_B, 1));

    // The stick: a small move stays dark, a real move wakes.
    darken(0);
    idle_set_axis_range(&s, ABS_X, 0, 4095);
    assert(axis(400000, ABS_X, 2048) && action == IDLE_NONE && idle_is_dark(&s));
    assert(axis(400010, ABS_X, 2048 + 400) && action == IDLE_NONE && idle_is_dark(&s));
    assert(axis(400020, ABS_X, 2048 + 900) && action == IDLE_WAKE && !idle_is_dark(&s));

    // A sync event never wakes and is swallowed while dark.
    darken(0);
    struct input_event syn = { .type = EV_SYN, .code = SYN_REPORT };
    assert(idle_on_event(&s, &syn, 400000, &action) && action == IDLE_NONE && idle_is_dark(&s));

    // A release lost to SYN_DROPPED: the kernel's key state ends swallowing.
    darken(0);
    assert(key(400000, BTN_A, 1) && action == IDLE_WAKE);
    assert(key(400010, BTN_A, 2));
    idle_keys_released(&s);
    assert(!s.swallowing && !key(400020, BTN_B, 1));
    assert(!key(400030, BTN_B, 0));

    // Idle mode off.
    idle_init(&s, 0);
    assert(idle_on_tick(&s, 10000000, 0) == IDLE_NONE && !idle_is_dark(&s));

    puts("idle: ok");
    return 0;
}
