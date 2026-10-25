#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12's buttons: ES by printed label, RetroArch by position (tests 62, 73).

The A12's face buttons are printed  Y X L (top row) / A B R (bottom row);
evtest on the A12 shows printed X = BTN_X (307) and printed Y = BTN_Y (308).
Joystick button numbers (RetroArch udev, SDL) follow the key codes in
ascending order, so they are derived here from the device tree. stick.cfg
and ES's controller.xml had X/Y swapped (SNES X and Y on the wrong
buttons) and ES had page up/down on R/L; KNULLI maps by label too.

In games the bottom row's A and B are left and right, the reverse of a
Nintendo pad (B left, A right), so they felt swapped (owner, 2026-10-21):
RetroArch maps the RetroPad by position (RetroPad A = the right button,
printed B; RetroPad B = printed A; X/Y already sit Nintendo-like), and its
RGUI swaps OK/cancel so that printed A still confirms, as in ES.
"""
import pathlib
import re
import xml.etree.ElementTree as ET

root = pathlib.Path(__file__).resolve().parents[5]
dts = (root / "projects/ROCKNIX/devices/RK3128/linux/dts/rockchip/rk3128-powkiddy-a12-rev-a.dts").read_text()
stick = dts[dts.index("stick {"):]
stick = stick[:stick.index("\n\t};")]
CODES = {"BTN_A": 0x130, "BTN_B": 0x131, "BTN_X": 0x133, "BTN_Y": 0x134, "BTN_TL": 0x136, "BTN_TR": 0x137,
         "BTN_SELECT": 0x13a, "BTN_START": 0x13b, "BTN_MODE": 0x13c, "BTN_DPAD_UP": 0x220,
         "BTN_DPAD_DOWN": 0x221, "BTN_DPAD_LEFT": 0x222, "BTN_DPAD_RIGHT": 0x223}
keys = dict(re.findall(r"label = \"([a-z-]+)\"; linux,code = <(\w+)>", stick))
buttons = sorted((CODES[c], label) for label, c in keys.items() if c.startswith("BTN_"))
index = {label: i for i, (_, label) in enumerate(buttons)}
assert index["a"] == 0 and index["x"] == 2 and index["y"] == 3, index

cfg = dict(re.findall(r'^input_(\w+)_btn = "(\d+)"', (root / "projects/ROCKNIX/packages/emulators/libretro/"
                       "retroarch/retroarch-joypads/gamepads/stick.cfg").read_text(), re.M))
for pad, label in {"a": "b", "b": "a", "x": "x", "y": "y", "l": "l", "r": "r", "select": "select",
                   "start": "start", "up": "up", "down": "down", "left": "left", "right": "right",
                   "enable_hotkey": "back"}.items():
    assert int(cfg[pad]) == index[label], (pad, cfg[pad], label, index[label])

es = ET.parse(root / "projects/ROCKNIX/packages/ui/emulationstation/config/RK3128/controller.xml")
ids = {i.get("name"): int(i.get("id")) for i in es.iter("input")}
for name, label in {"a": "a", "b": "b", "x": "x", "y": "y", "pageup": "l", "pagedown": "r",
                    "select": "select", "start": "start", "hotkeyenable": "back"}.items():
    assert ids[name] == index[label], (name, ids[name], label, index[label])
ra = (root / "projects/ROCKNIX/packages/emulators/libretro/retroarch/sources/RK3128/retroarch.cfg").read_text()
assert re.search(r'^menu_swap_ok_cancel_buttons = "true"$', ra, re.M), "RGUI must confirm with printed A"
print("controls mapping: ok")
