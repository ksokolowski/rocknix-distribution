#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-power follows the power source (power policy, 2026-10-26).

Unplugging sets the remembered battery brightness (40 % at first), plugging
in always sets 100 %; a change on battery becomes the new battery level, a
change on the charger is not kept. Wi-Fi power-save is on on battery only.
"Power saving" off (a12.powersave=0) leaves the brightness alone and Wi-Fi
power-save off. At <= 5 % while discharging, three readings in a row shut
the device down cleanly, whatever the switch says. The screen's dark state
(bl_power, owned by a12-controls) is never touched.
Review 2026-10-27: the script runs with ROCKNIX's real get_setting/set_setting
here (a stub hid that `set -u` broke them); the battery driver samples every
5 s, so a low reading must last 30 s, not three passes; a pass with nothing to
change starts no process (forks keep schedutil at 1200 MHz, test 77); the
service starts after rocknix-autostart (006-display sets the brightness).
"""
import shutil
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
functions = root / "projects/ROCKNIX/packages/rocknix/profile.d/001-functions"
script = root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/sources/a12-power"


class Device:
    def __init__(self, tmp, wifi=True):
        self.t = pathlib.Path(tmp)
        self.bat = self.t / "sys/class/power_supply/battery"
        self.bl = self.t / "sys/class/backlight/backlight"
        self.cfg = self.t / "storage/.config/system/configs/system.cfg"
        for d in (self.bat, self.bl, self.cfg.parent, self.t / "run", self.t / "bin", self.t / "sys/class/net"):
            d.mkdir(parents=True, exist_ok=True)
        if wifi:
            (self.t / "sys/class/net/wlan0").mkdir()
        (self.t / "sys/class/net/eth0").mkdir()
        self.status("Charging")
        self.capacity("80")
        (self.bl / "brightness").write_text("127\n")
        (self.bl / "max_brightness").write_text("255\n")
        (self.bl / "bl_power").write_text("0\n")
        self.cfg.write_text("display.brightness=50\n")
        self.now = 0
        for name in ("iw", "poweroff"):
            (self.t / "bin" / name).write_text(f'#!/bin/sh\necho "$*" >> "{self.t}/{name}.log"\n')
            (self.t / "bin" / name).chmod(0o755)

    def status(self, s):
        (self.bat / "status").write_text(s + "\n")

    def capacity(self, c):
        (self.bat / "capacity").write_text(c + "\n")

    def brightness(self, value=None):
        if value is not None:
            (self.bl / "brightness").write_text(f"{value}\n")
        return int((self.bl / "brightness").read_text())

    def setting(self, key):
        lines = [l for l in self.cfg.read_text().splitlines() if l.startswith(key + "=")]
        return lines[-1].split("=", 1)[1] if lines else None

    def log(self, name):
        f = self.t / f"{name}.log"
        return f.read_text().splitlines() if f.exists() else []

    def env(self):
        return dict(os.environ, A12_ROOT=str(self.t), A12_FUNCTIONS=str(functions), A12_NOW=str(self.now),
                    A12_IW=str(self.t / "bin/iw"), A12_POWEROFF=str(self.t / "bin/poweroff"))

    def run(self, after=2):
        self.now += after
        r = subprocess.run(["bash", str(script), "--once"], env=self.env(), capture_output=True, text=True)
        assert r.returncode == 0 and not r.stderr, r.stderr


with tempfile.TemporaryDirectory() as tmp:
    d = Device(tmp)
    d.run()                                   # boot on the charger
    assert d.brightness() == 255 and d.setting("display.brightness") == "100", d.brightness()
    assert d.log("iw")[-1] == "dev wlan0 set power_save off", d.log("iw")
    d.status("Discharging")
    d.run()
    assert d.brightness() == 102 and d.setting("display.brightness") == "40", d.brightness()
    assert d.log("iw")[-1] == "dev wlan0 set power_save on", d.log("iw")
    d.status("Charging")
    d.run()
    assert d.brightness() == 255 and d.setting("display.brightness") == "100"
    assert d.log("iw")[-1] == "dev wlan0 set power_save off"
    assert all(" eth0 " not in l for l in d.log("iw")), "only Wi-Fi interfaces"

    # The user's level on battery is remembered; a change on the charger is not.
    d.status("Discharging")
    d.run()
    d.brightness(153)
    d.run()
    assert d.setting("a12.brightness.battery") == "60", d.setting("a12.brightness.battery")
    d.status("Charging")
    d.run()
    assert d.brightness() == 255
    d.brightness(178)
    d.run()
    d.status("Discharging")
    d.run()
    assert d.brightness() == 153, d.brightness()
    d.status("Full")
    d.run()
    assert d.brightness() == 255, "Full counts as the charger"

    # Dark while unplugged: the level is set, the screen stays dark.
    (d.bl / "bl_power").write_text("4\n")
    d.status("Discharging")
    d.run()
    assert d.brightness() == 153 and (d.bl / "bl_power").read_text().strip() == "4"
    (d.bl / "bl_power").write_text("0\n")

    # Power saving off: no automatic brightness, no Wi-Fi power-save.
    d.status("Charging")
    d.run()
    d.brightness(127)
    with open(d.cfg, "a") as f:
        f.write("a12.powersave=0\n")
    d.status("Discharging")
    d.run()
    assert d.brightness() == 127, d.brightness()
    assert d.log("iw")[-1] == "dev wlan0 set power_save off"
    assert not d.log("poweroff")

with tempfile.TemporaryDirectory() as tmp:
    d = Device(tmp)
    d.status("Discharging")
    d.capacity("5")
    for _ in range(3):
        d.run()
    assert not d.log("poweroff"), "three passes within 6 s can be one 5 s battery sample"
    d.run(after=26)
    assert d.log("poweroff") == [""], d.log("poweroff")
    d.run()
    assert len(d.log("poweroff")) == 1, "shut down once"

with tempfile.TemporaryDirectory() as tmp:
    d = Device(tmp)
    d.status("Charging")
    d.capacity("3")
    for _ in range(4):
        d.run()
    assert not d.log("poweroff"), "never while charging"
    d.status("Discharging")
    for c, after in (("5", 2), ("5", 20), ("x", 2), ("5", 2), ("5", 20), ("12", 2), ("5", 20)):
        d.capacity(c)
        d.run(after=after)
    assert not d.log("poweroff"), "a bad or higher reading restarts the 30 s"

with tempfile.TemporaryDirectory() as tmp:
    d = Device(tmp)
    with open(d.cfg, "a") as f:
        f.write("a12.powersave=0\n")
    d.status("Discharging")
    d.capacity("4")
    d.run()
    d.run(after=30)
    assert d.log("poweroff") == [""], "the shutdown protects the card even with power saving off"

with tempfile.TemporaryDirectory() as tmp:
    d = Device(tmp, wifi=False)
    d.run()
    d.status("Discharging")
    d.run()
    assert not d.log("iw"), "no Wi-Fi, no iw call"
    assert d.brightness() == 102

with tempfile.TemporaryDirectory() as tmp:
    d = Device(tmp)
    d.status("Discharging")
    d.run()
    d.run()
    if shutil.which("strace"):
        trace = d.t / "trace"
        subprocess.run(["strace", "-f", "-qq", "-o", str(trace), "-e", "trace=clone,clone3,fork,vfork",
                        "bash", str(script), "--once"], env=d.env(), check=True)
        spawned = [l for l in trace.read_text().splitlines() if "clone" in l or "fork" in l]
        assert not spawned, f"a steady pass started {len(spawned)} processes"
        # Nor does it read system.cfg: settings are read again only when the
        # file is newer than the state (reading it line by line in bash
        # every 2 s cost 1.2 % of a core on the A12; 2026-10-28).
        trace.unlink()
        subprocess.run(["strace", "-qq", "-o", str(trace), "-e", "trace=openat",
                        "bash", str(script), "--once"], env=d.env(), check=True)
        assert "system.cfg" not in trace.read_text(), trace.read_text()
    # A change ES or the user makes is still seen on the next pass.
    with d.cfg.open("a") as f:
        f.write("a12.brightness.battery=70\n")
    d.status("Charging")
    d.run()
    d.status("Discharging")
    d.run()
    assert d.brightness() == 179, d.brightness()  # 70 % of 255, rounded

unit = (root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/sources/a12-power.service").read_text()
assert "After=" in unit and "rocknix-autostart.service" in unit.split("After=")[1].splitlines()[0]
mk = (root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/package.mk").read_text()
assert 'cp "${PKG_BUILD}/a12-power" "${INSTALL}/usr/bin/"' in mk and "enable_service a12-power.service" in mk
image = root / "build.ROCKNIX-RK3128.arm/image/system/usr"
if (image / "bin/a12-controls").is_file() and (image / "bin/a12-power").is_file():
    assert (image / "lib/systemd/system/a12-power.service").is_file()
print("power profile: ok")
