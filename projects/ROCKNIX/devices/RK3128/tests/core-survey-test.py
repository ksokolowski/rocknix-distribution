#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-core-survey turns the backlight off for the run and restores it.

Owner request (BACKLOG queue 9): no lit panel while the survey runs for an
hour. The script runs against a fake sysfs, systemctl and core-benchmark;
the backlight must read 0 while a core runs and its old value afterwards,
the governors must be restored, and FBNeo MK2 is in the list.
"""
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
script = (root / "projects/ROCKNIX/devices/RK3128/tools/bench/a12-core-survey").read_text()
assert "fbneo mame/mk2.zip" in script

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    sysfs = tmp / "sys"
    bl = sysfs / "class/backlight/backlight"
    cpu = sysfs / "devices/system/cpu/cpufreq/policy0"
    gpu = sysfs / "class/devfreq/10090000.gpu"
    dmc = sysfs / "class/devfreq/dmc"
    for d in (bl, cpu, gpu, dmc):
        d.mkdir(parents=True)
    (bl / "brightness").write_text("200\n")
    (cpu / "scaling_governor").write_text("schedutil\n")
    (gpu / "governor").write_text("simple_ondemand\n")
    (dmc / "cur_freq").write_text("456000000\n")
    base = tmp / "coretest"
    base.mkdir()
    bench = base / "core-benchmark"
    bench.write_text(f'#!/bin/sh\necho "backlight $(cat {bl}/brightness)"\n'
                     'echo "frames 3600-4200 in 1 s = 120.0 FPS; target 60.0 FPS"\n')
    bench.chmod(0o755)
    bindir = tmp / "bin"
    bindir.mkdir()
    (bindir / "systemctl").write_text('#!/bin/sh\n[ "$1" = is-active ] && echo active\nexit 0\n')
    (bindir / "systemctl").chmod(0o755)
    (tmp / "roms/mame").mkdir(parents=True)
    body = (script.replace("/storage/a12-coretest", str(base)).replace("/storage/roms", str(tmp / "roms"))
            .replace("/proc/sys/kernel/random/boot_id", "/dev/null").replace("/sys/", f"{sysfs}/")
            .replace("sleep 3", "true"))
    env = dict(os.environ, PATH=f"{bindir}:/usr/bin:/bin")
    out = tmp / "out"
    subprocess.run(["bash", "-c", body, "survey", str(out), "fbneo mame/mk2"], env=env, check=True,
                   capture_output=True)
    logs = list(out.glob("*-fbneo-mk2.log"))
    assert len(logs) == 1, list(out.iterdir())
    assert "backlight 0" in logs[0].read_text(), logs[0].read_text()
    assert (bl / "brightness").read_text().strip() == "200", "backlight restored"
    assert (cpu / "scaling_governor").read_text().strip() == "schedutil"
    assert (gpu / "governor").read_text().strip() == "simple_ondemand"
    assert "120.0" in (out / "summary.txt").read_text()
print("core survey: ok")
