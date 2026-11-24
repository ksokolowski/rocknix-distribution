#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 panel defaults to the 60-hblank timing (TEST_LOG 2026-10-10, test 49).

The legacy 60 Hz mode added vertical blanking (vtotal 664) and the owner saw
small vertical shaking; 60-hblank keeps the native vertical timing and adds
horizontal blanking, which removed the shaking. Its black lines were the
U-Boot LCDC QoS bug (tests 30-38). 54 MHz is GPLL 594 MHz / 11. It shows
each 60 fps frame once and is the default; panel_a12.refresh_60hz=0
selects the native 85 Hz mode.
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
patches = root / "projects/ROCKNIX/devices/RK3128/patches/linux"
p10 = (patches / "0010-a12-panel-and-ttl-phy-builtin.patch").read_text()
p13 = (patches / "0013-a12-panel-60hz-hblank-timing.patch").read_text()

# panel-a12.c as patch 0010 creates it, then patch 0013 on top.
hunk = p10.split("+++ b/drivers/gpu/drm/panel/panel-a12.c", 1)[1].split("\ndiff ", 1)[0]
source = "\n".join(l[1:] for l in hunk.splitlines() if l.startswith("+")) + "\n"
with tempfile.TemporaryDirectory() as tmp:
    f = pathlib.Path(tmp) / "drivers/gpu/drm/panel/panel-a12.c"
    f.parent.mkdir(parents=True)
    f.write_text(source)
    subprocess.run(["patch", "-p1", "-s", "-d", tmp], input=p13, text=True, check=True)
    code = f.read_text()

def mode(name):
    m = re.search(r"struct drm_display_mode " + name + r" = \{(.*?)\};", code, re.S)[1]
    return {k: int(v) for k, v in re.findall(r"\.(\w+) = (\d+)", m)}

native, sixty = mode("native"), mode("experimental")
assert native["clock"] == 75200 and native["htotal"] == 1354 and native["vtotal"] == 645, native
assert sixty["clock"] == 54000, sixty
assert (sixty["hsync_start"], sixty["hsync_end"], sixty["htotal"]) == (1184, 1194, 1395), sixty
for key in ("vdisplay", "vsync_start", "vsync_end", "vtotal"):
    assert sixty[key] == native[key], key  # native vertical timing kept
hz = sixty["clock"] * 1000 / (sixty["htotal"] * sixty["vtotal"])
assert abs(hz - 60.015) < 0.001, hz
assert re.search(r"^static bool refresh_60hz = true;$", code, re.M), "60 Hz is the default"
print("panel 60 Hz (60-hblank): ok")
