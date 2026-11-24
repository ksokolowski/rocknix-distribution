// SPDX-License-Identifier: GPL-2.0-or-later
// The daemon's idle actions on a fake root (power policy, 2026-10-26):
// darkening turns the backlight off with bl_power and, in ES, sets the GPU to
// its lowest frequency; waking and a restart of the daemon restore both.
// Review 2026-10-27: this kernel has no devfreq powersave governor, so the GPU
// is capped through max_freq (the A12 lists 200/300/400/480 MHz); the dark
// marker is written before the backlight goes off; a daemon that cannot
// find the stick still restores the screen; swallowing ends once the kernel
// reports no key down, even if a release event was lost.
#include <assert.h>
#include <stdlib.h>
#include <sys/stat.h>
#define main controls_main
#include "../packages/a12-controls/sources/a12-controls.c"
#undef main

static char root[] = "/tmp/a12-idle-root-XXXXXX";

static void put(const char *path, const char *text)
{
    char full[512], dir[512];
    snprintf(full, sizeof(full), "%s/%s", root, path);
    snprintf(dir, sizeof(dir), "%s", full);
    for (char *p = dir + strlen(root) + 1; (p = strchr(p, '/')); p++) {
        *p = 0;
        mkdir(dir, 0755);
        *p = '/';
    }
    FILE *f = fopen(full, "w");
    assert(f);
    fputs(text, f);
    fclose(f);
}

static const char *get(const char *path)
{
    static char text[128];
    char full[512];
    snprintf(full, sizeof(full), "%s/%s", root, path);
    FILE *f = fopen(full, "r");
    if (!f)
        return NULL;
    size_t n = fread(text, 1, sizeof(text) - 1, f);
    fclose(f);
    text[n] = 0;
    char *nl = strchr(text, '\n');
    if (nl)
        *nl = 0;
    return text;
}

#define BL "sys/class/backlight/backlight/bl_power"
#define GPU "sys/class/devfreq/10090000.gpu/governor"
#define GPUMAX "sys/class/devfreq/10090000.gpu/max_freq"
#define CFG "storage/.config/system/configs/system.cfg"
#define GAMES "sys/fs/cgroup/games.slice/cgroup.events"

int main(void)
{
    assert(mkdtemp(root));
    setenv("A12_ROOT", root, 1);
    put(BL, "0\n");
    put(GPU, "simple_ondemand\n");
    put(GPUMAX, "480000000\n");
    put("sys/class/devfreq/10090000.gpu/available_frequencies", "200000000 300000000 400000000 480000000\n");
    put(CFG, "display.brightness=50\n");
    put("run/.keep", "");
    put("sys/fs/cgroup/games.slice/cgroup.procs", "");
    put(GAMES, "populated 0\nfrozen 0\n");
    put("storage/.config/emulationstation/es_settings.cfg",
        "<?xml version=\"1.0\"?>\n<config>\n\t<int name=\"ScreenSaverTime\" value=\"120000\" />\n</config>\n");

    assert(a12_powersave_enabled());
    put(CFG, "display.brightness=50\na12.powersave=0\n");
    assert(!a12_powersave_enabled());
    put(CFG, "a12.powersave=1\n");
    assert(a12_powersave_enabled());

    // Games run in scopes below games.slice: the slice's own cgroup.procs
    // stays empty, cgroup.events says whether any of them is populated.
    assert(!a12_in_game());
    put(GAMES, "populated 1\nfrozen 0\n");
    assert(a12_in_game());
    put(GAMES, "populated 0\nfrozen 0\n");

    char *ms = a12_es_screensaver_ms();
    assert(ms && !strcmp(ms, "120000"));
    free(ms);
    put("storage/.config/emulationstation/es_settings.cfg", "<config>\n</config>\n");
    assert(a12_es_screensaver_ms() == NULL);

    a12_darken(-1, false);
    assert(!strcmp(get(BL), "4") && !strcmp(get(GPUMAX), "200000000") && !strcmp(get(GPU), "simple_ondemand"));
    assert(!strcmp(get("run/a12-idle.gpu"), "480000000") && get("run/a12-idle.dark"));
    a12_wake(-1);
    assert(!strcmp(get(BL), "0") && !strcmp(get(GPUMAX), "480000000") && !get("run/a12-idle.dark"));

    // In a game only the backlight goes off.
    a12_darken(-1, true);
    assert(!strcmp(get(BL), "4") && !strcmp(get(GPUMAX), "480000000"));
    a12_wake(-1);
    assert(!strcmp(get(BL), "0"));

    // The daemon restarted while dark: its start restores the screen.
    a12_darken(-1, false);
    a12_idle_restore();
    assert(!strcmp(get(BL), "0") && !strcmp(get(GPUMAX), "480000000") && !get("run/a12-idle.dark"));
    put(BL, "0\n");
    put(GPUMAX, "400000000\n");
    a12_idle_restore();
    assert(!strcmp(get(BL), "0") && !strcmp(get(GPUMAX), "400000000"));

    // The marker comes first, so a crash during sync() still leaves a way back.
    char source[1024];
    snprintf(source, sizeof(source), "%.*s/../packages/a12-controls/sources/a12-controls.c",
             (int)(strrchr(__FILE__, '/') - __FILE__), __FILE__);
    FILE *f = fopen(source, "r");
    assert(f);
    static char code[65536];
    code[fread(code, 1, sizeof(code) - 1, f)] = 0;
    fclose(f);
    char *darken = strstr(code, "void a12_darken(");
    assert(darken);
    char *marker = strstr(darken, "IDLE_DARK"), *backlight = strstr(darken, "BL_POWER");
    assert(marker && backlight && marker < backlight);

    // The stick is never grabbed (owner 2026-10-28): the wake press reaches
    // ES, which spends it ending its own screensaver, and games; only the
    // daemon's hotkeys swallow it.
    assert(!strstr(code, "EVIOCGRAB"));

    // No stick device (none under the fake root): the daemon gives up, but
    // not before restoring.
    put(BL, "4\n");
    put("run/a12-idle.dark", "");
    assert(controls_main() == 1);
    assert(!strcmp(get(BL), "0") && !get("run/a12-idle.dark"));

    // Key state from the kernel: all released.
    unsigned char keys[(KEY_MAX + 8) / 8] = {0};
    assert(keys_all_up(keys, sizeof(keys)));
    keys[BTN_A / 8] |= 1 << (BTN_A % 8);
    assert(!keys_all_up(keys, sizeof(keys)));

    puts("controls idle: ok");
    return 0;
}
