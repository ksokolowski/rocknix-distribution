#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12's commander prelude sits at upstream's path (sync 2026-10-23).

Upstream's commander.sh now reads one prelude, /usr/share/commander/
commander.cfg, installed by the commander package for H700, RK3326, RK3399,
RK3588 and S922X. The A12 keeps upstream's script unchanged and installs its
own prelude (A/B swapped for SDL, larger text, ROM paths) at that path from
a12-controls; the commander package must not install one for RK3128, or the
two would clash.
"""
import pathlib
import re

root = pathlib.Path(__file__).resolve().parents[5]
script = (root / "projects/ROCKNIX/packages/misc/modules/sources/commander.sh").read_text()
assert 'PRELUDE="/usr/share/commander/commander.cfg"' in script, "upstream's prelude path changed"
assert "HW_DEVICE" not in script, "commander.sh carries an A12 change again"

a12 = (root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/package.mk").read_text()
assert 'cp "${PKG_BUILD}/commander.cfg" "${INSTALL}/usr/share/commander/commander.cfg"' in a12, \
    "a12-controls must install its prelude at upstream's path"

cmd = (root / "projects/ROCKNIX/packages/apps/commander/package.mk").read_text()
cases = re.search(r"case \$\{DEVICE\} in\n\s*([^)]+)\)\n\s*cp -a \$\{PKG_DIR\}/config/commander.cfg", cmd)
assert cases and "RK3128" not in cases[1].split("|"), "commander package would install a second prelude on RK3128"
print("commander prelude: ok")
