#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-battery-run logs a battery run for the power-policy comparison.

One line per interval (60 s on the device): time, uptime, status, capacity,
voltage, brightness, bl_power and CPU governor, into
/storage/.cache/a12-diagnostics/battery-run-<boot id>.log, until the capacity
reaches 10 % or the tool is stopped. Baseline and policy runs use it alike.
"""
import os
import pathlib
import signal
import subprocess
import tempfile
import time

root = pathlib.Path(__file__).resolve().parents[5]
tool = root / "projects/ROCKNIX/devices/RK3128/tools/a12-battery-run"


def fake(tmp, capacity):
    t = pathlib.Path(tmp)
    files = {"sys/class/power_supply/battery/status": "Discharging", "sys/class/power_supply/battery/capacity": capacity,
             "sys/class/power_supply/battery/voltage_now": "3800000", "sys/class/backlight/backlight/brightness": "102",
             "sys/class/backlight/backlight/bl_power": "0",
             "sys/devices/system/cpu/cpufreq/policy0/scaling_governor": "schedutil",
             "proc/sys/kernel/random/boot_id": "b00700", "proc/uptime": "123.45 400.00"}
    for path, text in files.items():
        (t / path).parent.mkdir(parents=True, exist_ok=True)
        (t / path).write_text(text + "\n")
    (t / "storage/.cache/a12-diagnostics").mkdir(parents=True)
    return t, dict(os.environ, A12_ROOT=str(t), A12_INTERVAL="0.1")


with tempfile.TemporaryDirectory() as tmp:
    t, env = fake(tmp, "10")
    subprocess.run(["bash", str(tool)], env=env, check=True, timeout=10)
    log = (t / "storage/.cache/a12-diagnostics/battery-run-b00700.log").read_text().splitlines()
    assert log[0].startswith("# time uptime status capacity voltage brightness bl_power governor"), log
    fields = log[1].split()
    assert fields[1:] == ["123", "Discharging", "10", "3800000", "102", "0", "schedutil"], fields
    assert len(log) == 2, "it stops once the capacity is 10 % or less"

with tempfile.TemporaryDirectory() as tmp:
    t, env = fake(tmp, "80")
    p = subprocess.Popen(["bash", str(tool)], env=env)
    time.sleep(1)
    (t / "sys/class/power_supply/battery/capacity").write_text("79\n")
    time.sleep(0.5)
    p.send_signal(signal.SIGTERM)
    assert p.wait(timeout=5) == 0, "SIGTERM ends the run cleanly"
    log = (t / "storage/.cache/a12-diagnostics/battery-run-b00700.log").read_text().splitlines()
    caps = [l.split()[3] for l in log[1:]]
    assert len(caps) >= 5 and caps[0] == "80" and caps[-1] == "79", caps
print("battery run: ok")
