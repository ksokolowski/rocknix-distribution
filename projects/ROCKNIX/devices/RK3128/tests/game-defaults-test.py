#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""A12 game defaults: CPU performance governor unless chosen, 60 Hz refresh.

Owner decision 2026-10-11: games and emulators run with CPU and GPU at full
speed. RetroArch syncs to the panel refresh: by default the 60-hblank mode,
54 MHz / (1395 x 645) = 60.015 Hz (test 49); with panel_a12.refresh_60hz=0
the native mode, delivered as 594 MHz / 8 = 74.25 MHz / (1354 x 645).
Quirk 026-refresh_rate moves RetroArch between those two rates to match the
active panel mode and leaves any other rate alone.
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
refresh_quirk = root / "projects/ROCKNIX/packages/hardware/quirks/platforms/RK3128/026-refresh_rate"
quirk = root / "projects/ROCKNIX/packages/hardware/quirks/platforms/RK3128/015-game_settings"
retroarch = root / "projects/ROCKNIX/packages/emulators/libretro/retroarch/sources/RK3128/retroarch.cfg"

FUNCTIONS = r'''
J_CONF="$CFG"
set_setting() { sed -i "/^$1=/d" "$J_CONF"; echo "$1=$2" >> "$J_CONF"; }
'''


def run(initial):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        cfg = tmp / "system.cfg"
        cfg.write_text(initial)
        (tmp / "functions").write_text(FUNCTIONS)
        script = quirk.read_text().replace("/etc/profile.d/001-functions", str(tmp / "functions"))
        subprocess.run(["sh", "-c", script], check=True, env={"CFG": str(cfg), "PATH": "/usr/bin:/bin"})
        return cfg.read_text()


assert "global.cpugovernor=performance" in run("system.loglevel=none\n")
# system.cpugovernor is the frontend's governor; games still get the default.
both = run("system.cpugovernor=schedutil\n")
assert "system.cpugovernor=schedutil" in both and "global.cpugovernor=performance" in both, both
kept = run("global.cpugovernor=schedutil\n")
assert "global.cpugovernor=schedutil" in kept and "performance" not in kept, kept

RATE_60 = "60.015000"
RATE_NATIVE = "85.019409"
assert abs(float(RATE_60) - 54_000_000 / (1395 * 645)) < 1e-5
assert abs(float(RATE_NATIVE) - 74_250_000 / (1354 * 645)) < 1e-5
rate = re.search(r'^video_refresh_rate = "([0-9.]+)"$', retroarch.read_text(), re.M)[1]
assert rate == RATE_60, rate


def refresh(param, rate):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        cfg = tmp / "retroarch.cfg"
        cfg.write_text(f'video_driver = "gl"\nvideo_refresh_rate = "{rate}"\n')
        (tmp / "param").write_text(param + "\n")
        script = (refresh_quirk.read_text()
                  .replace("/storage/.config/retroarch/retroarch.cfg", str(cfg))
                  .replace("/sys/module/panel_a12/parameters/refresh_60hz", str(tmp / "param")))
        subprocess.run(["sh", "-c", script], check=True, env={"PATH": "/usr/bin:/bin"})
        text = cfg.read_text()
        assert 'video_driver = "gl"' in text, text
        return re.search(r'^video_refresh_rate = "([0-9.]+)"$', text, re.M)[1]


assert refresh("Y", RATE_NATIVE) == RATE_60
assert refresh("Y", RATE_60) == RATE_60
assert refresh("N", RATE_60) == RATE_NATIVE
assert refresh("N", RATE_NATIVE) == RATE_NATIVE
assert refresh("Y", "59.940000") == "59.940000"  # the user's own rate stays
print("a12 game defaults: ok")
