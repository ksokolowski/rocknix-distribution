#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""B12 step 6: the A12 builds without fbdev by default (test 61).

The pinned fbcon framebuffer (2.4 MB of CMA, test 46) existed only because
the splash used fbdev. By default the kernel drops fbdev and fbcon and the
command line gets a12_kms_splash, so the initramfs logo, update progress
(a12-update-splash) and every a12-splash mode use KMS. A12_NO_FBDEV=no
builds the old fbdev variant.
"""
import os
import pathlib
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
device = root / "projects/ROCKNIX/devices/RK3128"
options = (device / "options").read_text()
linux_mk = (root / "projects/ROCKNIX/packages/linux/package.mk").read_text()
config = (device / "linux/linux.arm.conf").read_text()


def cmdline(no_fbdev):
    env = dict(os.environ, A12_NO_FBDEV=no_fbdev)
    body = "".join(l for l in options.splitlines(True)
                   if l.startswith(("EXTRA_CMDLINE", "if [ \"${A12_NO_FBDEV}\"", "  EXTRA_CMDLINE+=", "fi")))
    out = subprocess.run(["bash", "-c", body + 'echo "$EXTRA_CMDLINE"'], env=env, capture_output=True,
                         text=True, check=True).stdout.split()
    return out


assert cmdline("")[-1] == "a12_kms_splash" and "quiet" in cmdline(""), "default: no fbdev"
assert cmdline("yes")[-1] == "a12_kms_splash"
assert "a12_kms_splash" not in cmdline("no"), "A12_NO_FBDEV=no keeps fbdev"
# Kernel: fbdev stays in the committed config; the build disables it unless A12_NO_FBDEV=no.
assert "CONFIG_DRM_FBDEV_EMULATION=y" in config and "CONFIG_FRAMEBUFFER_CONSOLE=y" in config
assert ('if [ "${DEVICE}" = "RK3128" ] && [ "${A12_NO_FBDEV}" != "no" ]; then\n'
        '    ${PKG_BUILD}/scripts/config --disable CONFIG_DRM_FBDEV_EMULATION \\\n'
        '      --disable CONFIG_FRAMEBUFFER_CONSOLE --disable CONFIG_FB') in linux_mk
# The boot splash must still start without /dev/fb0.
unit = (device / "packages/a12-controls/sources/a12-splash.service").read_text()
assert "ConditionPathExists=|/dev/dri/card0" in unit
print("no fbdev default: ok")
