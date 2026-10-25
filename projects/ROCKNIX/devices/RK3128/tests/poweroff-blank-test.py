#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 final screen stays lit only on an ordinary power-off.

Kernel patch 0012 keeps display and backlight on at power-off, because the
latching switch removes power. After a power-off on a nearly empty battery
or at a critical temperature, the lit screen kept draining the cell until
the switch was pressed (BACKLOG open issue). The systemd-shutdown hook now
blanks the screen and turns the backlight off in those cases.
"""
import os
import pathlib
import subprocess
import tempfile

hook = pathlib.Path(__file__).resolve().parents[1] / "packages/a12-controls/sources/a12-splash.shutdown-hook"


def run(verb, capacity="50", usb="0", temp="45000", crit="105000"):
    with tempfile.TemporaryDirectory() as tmp:
        sys = pathlib.Path(tmp) / "sys"
        bat, usbdir = sys / "class/power_supply/battery", sys / "class/power_supply/usb"
        zone, bl, fb = sys / "class/thermal/thermal_zone0", sys / "class/backlight/backlight", sys / "class/graphics/fb0"
        for d in (bat, usbdir, zone, bl, fb):
            d.mkdir(parents=True)
        (bat / "capacity").write_text(capacity + "\n")
        (usbdir / "online").write_text(usb + "\n")
        (zone / "temp").write_text(temp + "\n")
        (zone / "trip_point_0_type").write_text("passive\n")
        (zone / "trip_point_0_temp").write_text("1000\n")
        (zone / "trip_point_1_type").write_text("critical\n")
        (zone / "trip_point_1_temp").write_text(crit + "\n")
        (bl / "brightness").write_text("80\n")
        (bl / "bl_power").write_text("0\n")
        (fb / "blank").write_text("0\n")
        splash = pathlib.Path(tmp) / "a12-splash"
        splash.write_text(f'#!/bin/sh\necho "$1" > {tmp}/splash\n')
        splash.chmod(0o755)
        env = dict(os.environ, A12_SYSFS=str(sys), A12_SPLASH=str(splash))
        subprocess.run(["sh", str(hook), verb], env=env, check=True)
        shown = pathlib.Path(tmp, "splash")
        return (shown.read_text().strip() if shown.exists() else None,
                (bl / "brightness").read_text().strip(), (bl / "bl_power").read_text().strip(),
                (fb / "blank").read_text().strip())


lit = ("--final", "80", "0", "0")
dark = ("--blank", "0", "4", "4")   # backlight off, fb0 blanked, KMS CRTC disabled
assert run("poweroff") == lit, "ordinary power-off shows the final screen"
assert run("reboot")[0] is None and run("reboot")[1] == "80", "reboot is left alone"
assert run("poweroff", capacity="5") == dark, "empty battery: blank"
assert run("poweroff", capacity="6") == lit
assert run("poweroff", capacity="3", usb="1") == lit, "charging: the screen may stay"
assert run("poweroff", temp="105000") == dark, "critical temperature: blank"
assert run("poweroff", temp="104999") == lit, "passive trips do not count"
print("power-off blank: ok")
