#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""headphone_sense finds the A12 jack's event device.

2026-10-11: on the A12 the jack's handler line is `H: Handlers=event1 `, so
the first field is `Handlers=event1`; matching fields against ^event[0-9]+$
never succeeded and the script waited forever, so headphones were never
routed. Run the script's own awk lookup against both handler layouts.
"""
import pathlib
import re
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
script = (root / "projects/ROCKNIX/packages/sysutils/system-utils/sources/devices/RK3128/headphone_sense").read_text()
program = re.search(r"DEVICE=\$\(awk '(.*?)' /proc/bus/input/devices\)", script, re.S)[1]

# /proc/bus/input/devices ends handler lines with a space ({sp}).
DEVICES = """I: Bus=0019 Vendor=0001 Product=0001 Version=0100
N: Name="stick"
H: Handlers=kbd event0{sp}
B: EV=b

I: Bus=0000 Vendor=0000 Product=0000 Version=0000
N: Name="A12 Audio Headphones"
P: Phys=ALSA
H: Handlers={handlers}{sp}
B: SW=4

"""

for handlers, expected in (("event1", "/dev/input/event1"), ("kbd event7", "/dev/input/event7")):
    out = subprocess.run(["awk", program], input=DEVICES.format(handlers=handlers, sp=" "),
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == expected, (handlers, out)
print("headphone_sense lookup: ok")

# 2026-10-12 (test 55): at boot the codec's detect bit reads "inserted" with
# nothing plugged in, so the boot-time switch query routed ES's sound to HP and
# the speaker stayed silent until the path changed. Like KNULLI's udev hook,
# start on the speaker and follow only insertion events.
import os
import tempfile

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    devices = tmp / "devices"
    devices.write_text(DEVICES.format(handlers="event1", sp=" "))
    log = tmp / "log"
    bindir = tmp / "bin"
    bindir.mkdir()
    mocks = {
        # --query exits 10 when the switch is set: the false boot reading.
        "evtest": 'if [ "$1" = --query ]; then exit 10; fi\n'
                  'echo "Event: time 1.0, type 5 (EV_SW), code 2 (SW_HEADPHONE_INSERT), value 1"\n'
                  'echo "Event: time 2.0, type 5 (EV_SW), code 2 (SW_HEADPHONE_INSERT), value 0"',
        "amixer": f'echo "amixer $*" >> {log}',
    }
    for name, body in mocks.items():
        (bindir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bindir / name).chmod(0o755)
    profile = tmp / "profile"
    profile.write_text(f'set_setting() {{ echo "set $*" >> {log}; }}\n')
    body = (script.replace(". /etc/profile", f". {profile}")
            .replace("/proc/bus/input/devices", str(devices))
            .replace("/usr/bin/volume restore", ":"))
    env = dict(os.environ, PATH=f"{bindir}:/usr/bin:/bin")
    subprocess.run(["bash", "-c", body], env=env, check=True, timeout=10)
    calls = log.read_text().splitlines()
    paths = [c.split()[-1] for c in calls if c.startswith("amixer")]
    assert paths == ["SPK", "HP", "SPK"], calls
    assert calls[1] == "set audio.device speakers", calls
print("headphone_sense routing: ok")
