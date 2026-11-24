#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The first-boot resize shows its steps on the A12's KMS splash (sync9).

fs-resize runs from the system image in fs-resize.target, without
a12-splash.service and without a console the A12 can show (no fbcon). Its
progress meters call a12_update_splash (busybox functions), which runs
/usr/bin/a12-update-splash, but only the initramfs had that tool, so a
fresh card showed the bare logo for the whole resize (2026-10-24, the
first fresh-image boot of sync8). The system image now gets it too.
If a build is present, the image must contain it.
"""
import pathlib
import re

root = pathlib.Path(__file__).resolve().parents[5]
mk = (root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/package.mk").read_text()
functions = (root / "projects/ROCKNIX/packages/sysutils/busybox/scripts/functions").read_text()
resize = (root / "projects/ROCKNIX/packages/sysutils/busybox/scripts/fs-resize").read_text()


def body(name):
    return re.search(r"^%s\(\) \{\n(.*?)^\}\n" % name, mk, re.M | re.S)[1]


assert "a12-update-splash" in body("a12_build_update_splash")
assert re.search(r"^\s*a12_build_update_splash \S+", body("make_target"), re.M), \
    "the system build does not build a12-update-splash"
assert "freetype:host" in re.search(r'^PKG_DEPENDS_TARGET="([^"]*)"', mk, re.M)[1], \
    "the system build's glyph generator needs host FreeType"
assert re.search(r'cp \S*a12-update-splash "\$\{INSTALL\}/usr/bin/"', body("makeinstall_target")), \
    "a12-update-splash is not installed in the system image"
# The resize reaches the hook: it sources the functions and uses the meters.
assert ". /usr/lib/rocknix/functions" in resize and "StartProgressLog spinner" in resize
assert 'A12_UPDATE_SPLASH="${A12_UPDATE_SPLASH:-/usr/bin/a12-update-splash}"' in functions

image = root / "build.ROCKNIX-RK3128.arm/image/system/usr/bin"
if image.is_dir():
    assert (image / "a12-update-splash").is_file(), "built image lacks /usr/bin/a12-update-splash"
    print("resize progress: ok (built image checked)")
else:
    print("resize progress: ok")
