#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 keeps its last frame lit at power-off (boot splash plan, Task 7).

On hardware (2026-10-11) "It is safe to turn off your device" went black:
at power-off Linux runs the shutdown hooks of the Rockchip DRM driver
(disables the VOP), the A12 panel (powers it down) and pwm-backlight
(backlight off). The latching switch removes power, so the A12 leaves all
three on when it powers off; reboot still resets the display.
"""
import pathlib
import re

root = pathlib.Path(__file__).resolve().parents[5]
p = (root / "projects/ROCKNIX/devices/RK3128/patches/linux/0012-a12-keep-display-at-poweroff.patch").read_text()
files = re.findall(r"^\+\+\+ b/(\S+)", p, re.M)
assert files == ["drivers/gpu/drm/panel/panel-a12.c", "drivers/gpu/drm/rockchip/rockchip_drm_drv.c",
                 "drivers/video/backlight/pwm_bl.c"], files
for f in files:
    hunk = p.split(f"+++ b/{f}", 1)[1].split("\n--- a/", 1)[0]
    added = "\n".join(l[1:] for l in hunk.splitlines() if l.startswith("+"))
    assert "SYSTEM_POWER_OFF" in added, f
    if not f.endswith("panel-a12.c"):  # shared drivers: only on the A12 board
        assert 'of_machine_is_compatible("powkiddy,a12-rev-a")' in added, f
print("keep display at power-off: ok")
