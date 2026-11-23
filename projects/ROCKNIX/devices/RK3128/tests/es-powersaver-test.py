#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 ES default stops redrawing an idle menu (BACKLOG queue 5).

emulationstation-next's PowerSaver "default" mode wakes every 40 ms once
idle and renders each time (≈23 frames/s measured in test 49); "enhanced"
sleeps until input or the screensaver time. The RK3128 es_settings.cfg is
the one the emulationstation package installs for this device.
"""
import pathlib
import re
import xml.etree.ElementTree as ET

root = pathlib.Path(__file__).resolve().parents[5]
es = root / "projects/ROCKNIX/packages/ui/emulationstation"
cfg = ET.parse(es / "config/RK3128/es_settings.cfg").getroot()
values = {e.get("name"): e.get("value") for e in cfg}
assert values.get("PowerSaverMode") == "enhanced", values
assert values.get("ScreenSaverBehavior") == "black"
mk = (es / "package.mk").read_text()
assert re.search(r'cp "\$\{PKG_DIR\}/config/RK3128/es_settings.cfg" "\$\{INSTALL\}/usr/config/emulationstation/"', mk)
print("es power saver: ok")
