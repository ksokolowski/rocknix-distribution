// SPDX-License-Identifier: GPL-2.0-or-later
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <linux/input.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "a12-idle.h"

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

// Idle mode (power policy): paths are below A12_ROOT ("" on the device).
static void root_path(char *out, size_t size, const char *path)
{
    const char *root = getenv("A12_ROOT");
    snprintf(out, size, "%s%s", root ? root : "", path);
}

static bool read_line(const char *path, char *out, size_t size)
{
    char full[512];
    root_path(full, sizeof(full), path);
    FILE *f = fopen(full, "r");
    if (!f)
        return false;
    bool ok = fgets(out, (int)size, f) != NULL;
    fclose(f);
    if (ok)
        out[strcspn(out, "\n")] = 0;
    return ok;
}

static void write_text(const char *path, const char *text)
{
    char full[512];
    root_path(full, sizeof(full), path);
    FILE *f = fopen(full, "w");
    if (!f)
        return;
    fputs(text, f);
    fclose(f);
}

static bool exists(const char *path)
{
    char full[512];
    root_path(full, sizeof(full), path);
    return access(full, F_OK) == 0;
}

static void remove_file(const char *path)
{
    char full[512];
    root_path(full, sizeof(full), path);
    unlink(full);
}

static int open_stick(void)
{
    char pattern[512];
    glob_t paths;
    int found = -1;
    root_path(pattern, sizeof(pattern), "/dev/input/event*");
    if (glob(pattern, 0, NULL, &paths) != 0)
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

static bool keys_all_up(const unsigned char *keys, size_t size)
{
    for (size_t i = 0; i < size; i++)
        if (keys[i])
            return false;
    return true;
}

// A file of the GPU devfreq node, by the name pattern 010-governors uses.
static bool gpu_path(char *out, size_t size, const char *name)
{
    char pattern[512];
    glob_t paths;
    bool found = false;
    snprintf(out, size, "/sys/class/devfreq/*.gpu/%s", name);
    root_path(pattern, sizeof(pattern), out);
    if (glob(pattern, 0, NULL, &paths) == 0 && paths.gl_pathc > 0) {
        snprintf(out, size, "%s", paths.gl_pathv[0]);
        found = true;
    }
    globfree(&paths);
    return found;
}

static bool gpu_read(const char *name, char *out, size_t size)
{
    char path[512];
    if (!gpu_path(path, sizeof(path), name))
        return false;
    FILE *f = fopen(path, "r");
    if (!f)
        return false;
    bool ok = fgets(out, (int)size, f) != NULL;
    fclose(f);
    if (ok)
        out[strcspn(out, "\n")] = 0;
    return ok;
}

static void gpu_write(const char *name, const char *value)
{
    char path[512];
    if (!gpu_path(path, sizeof(path), name))
        return;
    FILE *f = fopen(path, "w");
    if (!f)
        return;
    fputs(value, f);
    fclose(f);
}

// The kernel has no devfreq powersave governor: cap max_freq at the lowest
// available frequency instead.
static bool gpu_lowest(char *out, size_t size)
{
    char list[256], *end;
    unsigned long lowest = 0;
    if (!gpu_read("available_frequencies", list, sizeof(list)))
        return false;
    for (char *p = list; *p; p = end) {
        unsigned long freq = strtoul(p, &end, 10);
        if (end == p)
            break;
        if (!lowest || freq < lowest)
            lowest = freq;
    }
    if (!lowest)
        return false;
    snprintf(out, size, "%lu", lowest);
    return true;
}

bool a12_powersave_enabled(void)
{
    char full[512], line[256];
    bool enabled = true;
    root_path(full, sizeof(full), "/storage/.config/system/configs/system.cfg");
    FILE *f = fopen(full, "r");
    if (!f)
        return true;
    while (fgets(line, sizeof(line), f))
        if (!strncmp(line, "a12.powersave=", 14))
            enabled = line[14] != '0';
    fclose(f);
    return enabled;
}

// Games run in scopes below games.slice, so the slice's own cgroup.procs is
// empty; cgroup.events says whether any process is inside.
bool a12_in_game(void)
{
    char full[512], line[64];
    bool populated = false;
    root_path(full, sizeof(full), "/sys/fs/cgroup/games.slice/cgroup.events");
    FILE *f = fopen(full, "r");
    if (!f)
        return false;
    while (fgets(line, sizeof(line), f))
        if (!strncmp(line, "populated ", 10))
            populated = line[10] == '1';
    fclose(f);
    return populated;
}

char *a12_es_screensaver_ms(void)
{
    char full[512], line[256];
    char *value = NULL;
    root_path(full, sizeof(full), "/storage/.config/emulationstation/es_settings.cfg");
    FILE *f = fopen(full, "r");
    if (!f)
        return NULL;
    while (!value && fgets(line, sizeof(line), f)) {
        char *v;
        if (!strstr(line, "\"ScreenSaverTime\"") || !(v = strstr(line, "value=\"")))
            continue;
        v += 7;
        value = strndup(v, strcspn(v, "\""));
    }
    fclose(f);
    return value;
}

#define BL_POWER "/sys/class/backlight/backlight/bl_power"
#define IDLE_DARK "/run/a12-idle.dark"
#define IDLE_GPU "/run/a12-idle.gpu"

void a12_darken(int fd, bool in_game)
{
    (void)fd;
    write_text(IDLE_DARK, "");
    write_text(BL_POWER, "4");
    if (!in_game) {
        char max[64], lowest[64];
        sync();
        if (gpu_read("max_freq", max, sizeof(max)) && gpu_lowest(lowest, sizeof(lowest))) {
            write_text(IDLE_GPU, max);
            gpu_write("max_freq", lowest);
        }
    }
}

void a12_wake(int fd)
{
    char max[64];
    (void)fd;
    write_text(BL_POWER, "0");
    if (read_line(IDLE_GPU, max, sizeof(max)) && max[0])
        gpu_write("max_freq", max);
    remove_file(IDLE_GPU);
    remove_file(IDLE_DARK);
}

void a12_idle_restore(void)
{
    if (exists(IDLE_DARK))
        a12_wake(-1);
}

static long long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static volatile sig_atomic_t stopping;

static void on_term(int sig)
{
    (void)sig;
    stopping = 1;
}

int main(void)
{
    struct input_event event;
    unsigned char keys[(KEY_MAX + 8) / 8];
    int fd = open_stick();
    bool syncing = false, waking = false, enabled = true, in_game = false;
    struct idle_state idle;
    int timeout = 0;
    long long refreshed = -10000;
    struct sigaction term = { .sa_handler = on_term };
    a12_idle_restore();
    if (fd < 0)
        return 1;
    sigaction(SIGTERM, &term, NULL);
    idle_init(&idle, now_ms());
    for (unsigned code = 0; code < ABS_CNT; code++) {
        struct input_absinfo info;
        if (ioctl(fd, EVIOCGABS(code), &info) >= 0)
            idle_set_axis_range(&idle, code, info.minimum, info.maximum);
    }
    memset(keys, 0, sizeof(keys));
    if (ioctl(fd, EVIOCGKEY(sizeof(keys)), keys) >= 0)
        restore_modifiers(keys);
    while (!stopping) {
        long long now = now_ms();
        if (now - refreshed >= 5000) {
            char *ms = a12_es_screensaver_ms();
            enabled = a12_powersave_enabled();
            in_game = a12_in_game();
            timeout = idle_timeout_ms(in_game, ms);
            free(ms);
            refreshed = now;
        }
        if (idle_on_tick(&idle, now, enabled ? timeout : 0) == IDLE_DARKEN) {
            a12_darken(fd, in_game);
            waking = true;
        }
        struct pollfd pfd = { .fd = fd, .events = POLLIN };
        int ready = poll(&pfd, 1, 1000);
        if (ready < 0 && errno == EINTR)
            continue;
        if (ready <= 0)
            continue;
        ssize_t size = read(fd, &event, sizeof(event));
        if (size < 0 && errno == EINTR)
            continue;
        if (size != sizeof(event))
            break;
        enum idle_action action;
        bool swallowed = idle_on_event(&idle, &event, now_ms(), &action);
        if (action == IDLE_WAKE)
            a12_wake(fd);
        if (idle.swallowing && event.type == EV_SYN) {
            memset(keys, 0, sizeof(keys));
            if (ioctl(fd, EVIOCGKEY(sizeof(keys)), keys) >= 0 && keys_all_up(keys, sizeof(keys)))
                idle_keys_released(&idle);
        }
        if (waking && !idle_is_dark(&idle) && !idle.swallowing) {
            waking = false;
            syncing = false;
            memset(keys, 0, sizeof(keys));
            if (ioctl(fd, EVIOCGKEY(sizeof(keys)), keys) >= 0)
                restore_modifiers(keys);
            else
                back_held = select_held = start_held = exit_held = false;
        }
        if (swallowed)
            continue;
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
    a12_idle_restore();
    close(fd);
    return stopping ? 0 : 1;
}
