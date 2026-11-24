#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""A USB keyboard behaves like a keyboard (2026-10-29).

ES: ROCKNIX ships a RetroArch-style keyboard map (X accept, Z back, Enter
menu), so on the A12 Enter opened the menu and Esc did nothing. The RK3128
build replaces it with ES's own PC-style default (Enter, Esc, F1, F2).

RetroArch: keyboard hotkeys (Esc quits, F1 menu) and keyboard_gamepad_enable
took keys away from computer cores. Game focus gives the whole keyboard to
the core; Detect turns it on for cores with a keyboard callback (VICE,
DOSBox Pure, cap32, atari800); uae4arm, blueMSX and Fuse only poll the
keyboard, so their overrides turn it on.
"""
import pathlib
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

root = pathlib.Path(__file__).resolve().parents[5]
es = root / "projects/ROCKNIX/packages/ui/emulationstation"
mk = (es / "package.mk").read_text()
merge = re.search(r"<<'PYCFG'\n(.*?)\nPYCFG", mk, re.S)[1]

with tempfile.TemporaryDirectory() as tmp:
    out = pathlib.Path(tmp) / "es_input.cfg"
    out.write_text((es / "config/common/es_input.cfg").read_text())
    subprocess.run([sys.executable, "-c", merge, str(out), str(es / "config/RK3128/controller.xml")], check=True)
    configs = ET.parse(out).getroot().findall("inputConfig")

keyboards = [c for c in configs if c.get("type") == "keyboard"]
assert len(keyboards) == 1, f"{len(keyboards)} keyboard configs"
keys = {i.get("name"): int(i.get("id")) for i in keyboards[0]}
want = {"a": 13, "b": 27, "start": 1073741882, "select": 1073741883, "hotkeyenable": 1073741883,
        "up": 1073741906, "down": 1073741905, "left": 1073741904, "right": 1073741903,
        "pageup": 1073741899, "pagedown": 1073741902, "x": 32, "y": 8}
assert keys == want, f"keyboard map {keys}"
sticks = [c for c in configs if c.get("deviceName") == "stick"]
assert len(sticks) == 1, "the A12 controls keep their mapping"

ra = root / "projects/ROCKNIX/packages/emulators/libretro/retroarch/sources/RK3128"
cfg = (ra / "retroarch.cfg").read_text()
assert re.search(r'^input_auto_game_focus = "2"$', cfg, re.M), "game focus on detect"
for core in ("uae4arm", "blueMSX", "Fuse"):
    override = (ra / f"config/{core}/{core}.cfg").read_text()
    assert re.search(r'^input_auto_game_focus = "1"$', override, re.M), f"{core} game focus on"
print("keyboard and mouse: ok")
