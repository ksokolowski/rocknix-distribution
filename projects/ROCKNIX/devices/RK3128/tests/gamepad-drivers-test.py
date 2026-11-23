#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""USB gamepads beyond plain HID load their own drivers (2026-10-28).

Both USB-A ports are hosts (usb-otg-host-test.py), so extra pads can be
plugged in. hid-generic covers plain HID pads; Xbox/XInput pads need xpad,
DualShock 4/DualSense hid-playstation and Switch pads hid-nintendo. The
whole joystick class was off. All three are modules, loaded only when such
a pad is plugged in, with rumble.
"""
import pathlib
import re

config = (pathlib.Path(__file__).resolve().parents[1] / "linux/linux.arm.conf").read_text()


def value(name):
    m = re.search(rf"^CONFIG_{name}=(\S+)$", config, re.M)
    return m[1] if m else None


assert value("INPUT_JOYSTICK") == "y", "joystick class"
for name in ("JOYSTICK_XPAD", "HID_PLAYSTATION", "HID_NINTENDO"):
    assert value(name) == "m", f"{name} as a module, got {value(name)}"
for name in ("JOYSTICK_XPAD_FF", "PLAYSTATION_FF", "NINTENDO_FF"):
    assert value(name) == "y", f"{name} rumble, got {value(name)}"
assert value("HID_GENERIC") == "y", "plain HID pads keep working"
print("gamepad drivers: ok")
