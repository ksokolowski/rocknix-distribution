#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""core-benchmark's warm-up and stage count are configurable.

The archived KNULLI baseline timed frames 60-660; the default (1200 warm-up,
three stages) measures later attract-mode scenes, so the two are not comparable.

For checking that a core optimisation keeps the picture bit-exact (beetle_vb
anaglyph, 2026-10-21): A12_BENCH_FRAMEHASH=1 prints a hash of every video
frame ("hash N HEX", rows of width*bytes only, pitch padding excluded), and
A12_BENCH_PRESS=N holds RetroPad Start and A for 5 of every N frames so games
move past their title, precaution and alignment screens. A12_BENCH_OPT=
"key=value;key=value" overrides core options (default: each option's first
value), e.g. vb_anaglyph_preset=red & blue to exercise the right eye.
"""
import os
import pathlib
import subprocess
import tempfile

bench = pathlib.Path(__file__).resolve().parents[1] / "tools/bench"
stub = r'''
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "libretro.h"
static int frames;
static retro_video_refresh_t vcb;
static retro_input_state_t icb;
static retro_input_poll_t pcb;
static unsigned char fb[4 * 8 * 16];  /* 4x4 XRGB pixels, pitch 32 bytes: half is padding */
static retro_environment_t ecb;
void retro_set_environment(retro_environment_t cb) {
    static const struct retro_variable v[] = { { "stub_color", "Color; red|blue|green" }, { NULL, NULL } };
    ecb = cb;
    cb(RETRO_ENVIRONMENT_SET_VARIABLES, (void *)v);
}
void retro_set_video_refresh(retro_video_refresh_t cb) { vcb = cb; }
void retro_set_audio_sample(retro_audio_sample_t cb) { (void)cb; }
void retro_set_audio_sample_batch(retro_audio_sample_batch_t cb) { (void)cb; }
void retro_set_input_poll(retro_input_poll_t cb) { pcb = cb; }
void retro_set_input_state(retro_input_state_t cb) { icb = cb; }
void retro_init(void) {}
void retro_deinit(void) {}
void retro_run(void) {
    frames++;
    if (pcb) pcb();
    int start = icb ? icb(0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_START) : 0;
    /* Cores that use input bitmasks (beetle_vb) ask for all buttons at once. */
    int mask = icb ? icb(0, RETRO_DEVICE_JOYPAD, 0, RETRO_DEVICE_ID_JOYPAD_MASK) : 0;
    if (start != !!(mask & (1 << RETRO_DEVICE_ID_JOYPAD_START)) ||
        start != !!(mask & (1 << RETRO_DEVICE_ID_JOYPAD_A))) fputs("MISMATCH\n", stderr);
    memset(fb, 0xEE, sizeof(fb));                       /* padding: must not count */
    for (int y = 0; y < 4; y++)
        for (int x = 0; x < 16; x++) fb[y * 32 + x] = (unsigned char)(frames + y + x + start * 100);
    struct retro_variable q = { "stub_color", NULL };
    if (frames == 1 && ecb && ecb(RETRO_ENVIRONMENT_GET_VARIABLE, &q) && q.value) fprintf(stderr, "COLOR=%s\n", q.value);
    if (vcb) vcb(fb, 4, 4, 32);
}
void retro_unload_game(void) {}
bool retro_load_game(const struct retro_game_info *game) { (void)game; return true; }
void retro_get_system_av_info(struct retro_system_av_info *info) { memset(info, 0, sizeof(*info)); info->timing.fps = 60.0; }
'''
with tempfile.TemporaryDirectory() as temporary:
    root = pathlib.Path(temporary)
    (root / "stub.c").write_text(stub)
    subprocess.run(["gcc", "-shared", "-fPIC", "-I", str(bench), "-o", str(root / "stub.so"), str(root / "stub.c")], check=True)
    subprocess.run(["gcc", "-Wall", "-I", str(bench), "-o", str(root / "cb"), str(bench / "core-benchmark.c"), "-ldl"], check=True)
    # Cores without need_fullpath get the content in memory, so it must exist.
    (root / "rom").write_bytes(b"\0" * 16)
    env = dict(os.environ, A12_BENCH_WARMUP="60", A12_BENCH_STAGES="1")
    out = subprocess.run([str(root / "cb"), str(root / "stub.so"), str(root / "rom")], env=env, capture_output=True, text=True, check=True).stdout
    lines = [line for line in out.splitlines() if " FPS" in line]
    assert len(lines) == 1 and lines[0].startswith("frames 60-660 "), out
    default = subprocess.run([str(root / "cb"), str(root / "stub.so"), str(root / "rom")], capture_output=True, text=True, check=True).stdout
    assert [line.split(" in ")[0] for line in default.splitlines() if " FPS" in line] == \
        ["frames 1200-1800", "frames 1800-2400", "frames 2400-3000"], default
    # Frame hashes and Start presses.
    env = dict(os.environ, A12_BENCH_WARMUP="0", A12_BENCH_STAGES="1", A12_BENCH_FRAMEHASH="1")
    run = lambda e: subprocess.run([str(root / "cb"), str(root / "stub.so"), str(root / "rom")], env=e,
                                   capture_output=True, text=True, check=True).stdout
    out = run(env)
    hashes = [l.split() for l in out.splitlines() if l.startswith("hash ")]
    assert len(hashes) == 600 and hashes[0][1] == "1" and hashes[-1][1] == "600", hashes[:2]
    assert run(env) == out or [h for h in run(env).splitlines() if h.startswith("hash ")] == \
        [l for l in out.splitlines() if l.startswith("hash ")]	# deterministic
    assert len({h[2] for h in hashes}) > 200	# frames differ
    p = subprocess.run([str(root / "cb"), str(root / "stub.so"), str(root / "rom")], env=dict(env, A12_BENCH_PRESS="10"),
                       capture_output=True, text=True, check=True)
    assert "MISMATCH" not in p.stderr, "bitmask input differs from per-button input"
    pressed = [l.split() for l in p.stdout.splitlines() if l.startswith("hash ")]
    differ = [i for i, (a, b) in enumerate(zip(hashes, pressed)) if a[2] != b[2]]
    assert len(differ) == 300, len(differ)	# Start held 5 of every 10 frames
    # Core options: first value by default, A12_BENCH_OPT overrides.
    err = lambda e: subprocess.run([str(root / "cb"), str(root / "stub.so"), str(root / "rom")], env=e,
                                   capture_output=True, text=True, check=True).stderr
    assert "COLOR=red" in err(env), err(env)
    assert "COLOR=green" in err(dict(env, A12_BENCH_OPT="other=x;stub_color=green")), err(dict(env, A12_BENCH_OPT="stub_color=green"))
    assert "COLOR=red & blue" in err(dict(env, A12_BENCH_OPT="stub_color=red & blue"))	# values with spaces
    # Padding bytes beyond width*4 are not hashed.
print("core benchmark: ok")
