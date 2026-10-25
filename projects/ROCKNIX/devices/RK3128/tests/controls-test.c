// SPDX-License-Identifier: GPL-2.0-or-later
#include <assert.h>
#define main controls_main
#include "../packages/a12-controls/sources/a12-controls.c"
#undef main

static int calls;
static const char *last_command;
static const char *last_direction;

static void record(const char *command, const char *direction)
{
    calls++;
    last_command = command;
    last_direction = direction;
}

static void send_key(unsigned short code, int value)
{
    struct input_event event = { .type = EV_KEY, .code = code, .value = value };
    handle_event(&event, record);
}

int main(void)
{
    send_key(KEY_VOLUMEUP, 1);
    assert(calls == 1 && !strcmp(last_command, "/usr/bin/volume"));
    assert(!strcmp(last_direction, "up"));
    send_key(KEY_VOLUMEUP, 0);
    send_key(BTN_MODE, 1);
    assert(calls == 1);
    send_key(KEY_VOLUMEDOWN, 1);
    assert(calls == 2 && !strcmp(last_command, "/usr/bin/brightness"));
    assert(!strcmp(last_direction, "down"));
    send_key(KEY_VOLUMEDOWN, 2);
    assert(calls == 3);
    send_key(BTN_MODE, 0);
    send_key(KEY_VOLUMEDOWN, 1);
    assert(calls == 4 && !strcmp(last_command, "/usr/bin/volume"));
    send_key(BTN_A, 1);
    send_key(KEY_VOLUMEDOWN, 0);
    assert(calls == 4);
    send_key(BTN_SELECT, 1);
    send_key(KEY_VOLUMEUP, 1);
    assert(calls == 5 && !strcmp(last_command, "/usr/bin/brightness"));
    assert(!strcmp(last_direction, "up"));
    send_key(BTN_MODE, 1);
    send_key(BTN_SELECT, 0);
    send_key(KEY_VOLUMEDOWN, 1);
    assert(calls == 6 && !strcmp(last_command, "/usr/bin/brightness"));
    send_key(BTN_MODE, 0);
    send_key(KEY_VOLUMEUP, 1);
    assert(calls == 7 && !strcmp(last_command, "/usr/bin/volume"));
    unsigned char keys[(KEY_MAX + 8) / 8] = {0};
    keys[BTN_MODE / 8] |= 1 << (BTN_MODE % 8);
    restore_modifiers(keys);
    send_key(KEY_VOLUMEUP, 1);
    assert(calls == 8 && !strcmp(last_command, "/usr/bin/brightness"));
    memset(keys, 0, sizeof(keys));
    keys[BTN_SELECT / 8] |= 1 << (BTN_SELECT % 8);
    restore_modifiers(keys);
    send_key(KEY_VOLUMEUP, 1);
    assert(calls == 9 && !strcmp(last_command, "/usr/bin/brightness"));
    memset(keys, 0, sizeof(keys));
    restore_modifiers(keys);
    send_key(KEY_VOLUMEUP, 1);
    assert(calls == 10 && !strcmp(last_command, "/usr/bin/volume"));
    send_key(BTN_START, 1);
    assert(calls == 10);
    send_key(BTN_SELECT, 1);
    assert(calls == 11 && !strcmp(last_command, "/usr/bin/a12-exit-game"));
    send_key(BTN_SELECT, 2);
    send_key(BTN_START, 2);
    assert(calls == 11);
    send_key(BTN_START, 0);
    send_key(BTN_START, 1);
    assert(calls == 12);
    send_key(BTN_START, 0);
    send_key(BTN_SELECT, 0);
    send_key(BTN_SELECT, 1);
    send_key(BTN_START, 1);
    assert(calls == 13);
    keys[BTN_SELECT / 8] |= 1 << (BTN_SELECT % 8);
    keys[BTN_START / 8] |= 1 << (BTN_START % 8);
    restore_modifiers(keys);
    send_key(BTN_START, 2);
    assert(calls == 13);
    memset(keys, 0, sizeof(keys));
    restore_modifiers(keys);
    send_key(BTN_START, 1);
    send_key(BTN_SELECT, 1);
    assert(calls == 14);
    return 0;
}
