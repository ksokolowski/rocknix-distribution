#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""ES shows one "Power saving" switch on the A12 (power policy, 2026-10-26).

It stores a12.powersave ("1" on, "0" off; absent counts as on), which
a12-controls (idle mode) and a12-power (brightness per power source) read.
The patch must apply to the pinned ES source after the A12's patches
0001-0003; that check runs when the source tarball is in sources/.
"""
import pathlib
import re
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
patches = root / "projects/ROCKNIX/devices/RK3128/patches/emulationstation"
patch = patches / "0004-menu-power-saving-switch-on-rk3128.patch"
text = patch.read_text()
assert "#if defined(RK3128)" in text and '"a12.powersave"' in text
assert '_("POWER SAVING")' in text
assert '_("Dims the screen on battery and turns it off when idle. Games always run at full speed.")' in text
assert re.search(r'get\("a12\.powersave"\) != "0"', text), "absent or 1 counts as on"

version = re.search(r'^PKG_VERSION="([0-9a-f]+)"',
                    (root / "projects/ROCKNIX/packages/ui/emulationstation/package.mk").read_text(), re.M)[1]
tarball = root / f"sources/emulationstation/emulationstation-{version}.tar.gz"
if not tarball.is_file():
    print("es powersave patch: ok (SKIP apply: ES source not downloaded)")
    raise SystemExit(0)
with tempfile.TemporaryDirectory() as tmp:
    with tarfile.open(tarball) as t:
        t.extractall(tmp, filter="data")
    src = next(pathlib.Path(tmp).iterdir())
    for p in sorted(patches.glob("*.patch")):
        r = subprocess.run(["patch", "-p1", "--forward", "-i", str(p)], cwd=src, capture_output=True, text=True)
        assert r.returncode == 0, f"{p.name} does not apply:\n{r.stdout}{r.stderr}"
    menu = (src / "es-app/src/guis/GuiMenu.cpp").read_text()
    assert menu.index('_("SCREEN BRIGHTNESS")') < menu.index('_("POWER SAVING")'), "next to the brightness entry"
print("es powersave patch: ok")
