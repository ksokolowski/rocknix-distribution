// SPDX-License-Identifier: GPL-2.0-or-later
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <linux/input.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <unistd.h>

static bool back_held, select_held, start_held, exit_held;

static void restore_modifiers(const unsigned char *keys)
{
    back_held = (keys[BTN_MODE / 8] & (1 << (BTN_MODE % 8))) ||
                (keys[BTN_BACK / 8] & (1 << (BTN_BACK % 8)));
    select_held = (keys[BTN_SELECT / 8] & (1 << (BTN_SELECT % 8))) != 0;
    start_held = (keys[BTN_START / 8] & (1 << (BTN_START % 8))) != 0;
    exit_held = select_held && start_held;
}

static void dispatch(const char *command, const char *direction)
{
    pid_t child = fork();
    if (child == 0) {
        execl(command, command, direction, (char *)NULL);
        _exit(127);
    }
    if (child > 0)
        while (waitpid(child, NULL, 0) < 0 && errno == EINTR) {}
}

static void handle_event(const struct input_event *event,
                         void (*action)(const char *, const char *))
{
    if (event->type != EV_KEY)
        return;
    if (event->code == BTN_MODE || event->code == BTN_BACK) {
        back_held = event->value != 0;
        return;
    }
    if (event->code == BTN_SELECT || event->code == BTN_START) {
        if (event->code == BTN_SELECT)
            select_held = event->value != 0;
        else
            start_held = event->value != 0;
        bool chord = select_held && start_held;
        if (chord && !exit_held)
            action("/usr/bin/a12-exit-game", "");
        exit_held = chord;
        return;
    }
    if (event->value != 1 && event->value != 2)
        return;
    if (event->code == KEY_VOLUMEUP || event->code == KEY_VOLUMEDOWN)
        action(back_held || select_held ? "/usr/bin/brightness" : "/usr/bin/volume",
               event->code == KEY_VOLUMEUP ? "up" : "down");
}

static int open_stick(void)
{
    glob_t paths;
    int found = -1;
    if (glob("/dev/input/event*", 0, NULL, &paths) != 0)
        return -1;
    for (size_t i = 0; i < paths.gl_pathc; i++) {
        char name[128] = {0};
        int fd = open(paths.gl_pathv[i], O_RDONLY | O_CLOEXEC);
        if (fd < 0)
            continue;
        if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) >= 0 && !strcmp(name, "stick")) {
            unsigned int repeat[2] = {400, 150};
            if (ioctl(fd, EVIOCSREP, repeat) < 0)
                perror("stick repeat interval");
            found = fd;
            break;
        }
        close(fd);
    }
    globfree(&paths);
    return found;
}

int main(void)
{
    struct input_event event;
    unsigned char keys[(KEY_MAX + 8) / 8];
    int fd = open_stick();
    bool syncing = false;
    if (fd < 0)
        return 1;
    memset(keys, 0, sizeof(keys));
    if (ioctl(fd, EVIOCGKEY(sizeof(keys)), keys) >= 0)
        restore_modifiers(keys);
    while (true) {
        ssize_t size = read(fd, &event, sizeof(event));
        if (size < 0 && errno == EINTR)
            continue;
        if (size != sizeof(event))
            break;
        if (event.type == EV_SYN && event.code == SYN_DROPPED) {
            syncing = true;
            continue;
        }
        if (syncing) {
            if (event.type == EV_SYN && event.code == SYN_REPORT) {
                memset(keys, 0, sizeof(keys));
                if (ioctl(fd, EVIOCGKEY(sizeof(keys)), keys) >= 0)
                    restore_modifiers(keys);
                else
                    back_held = select_held = start_held = exit_held = false;
                syncing = false;
            }
            continue;
        }
        handle_event(&event, dispatch);
    }
    close(fd);
    return 1;
}
