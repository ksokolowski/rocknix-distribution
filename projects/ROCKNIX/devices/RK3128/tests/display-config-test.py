#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 RGB clock edge follows the panel's bus flags; the backlight is linear.

2026-10-09 (boot c80ba292): the owner compared rgb_dclk_pol=1 (mainline) and 0
(KNULLI, pixelclk-active=1) on a test pattern; mainline added patterns to grey
areas and colour transitions, KNULLI's edge did not.
"""
import pathlib
import re

device = pathlib.Path(__file__).resolve().parents[1]
patch = (device / "patches/linux/0008-rgb-dclk-polarity-from-bus-flags.patch").read_text()
vop_hunk = patch.split("rockchip_drm_vop.c", 1)
assert len(vop_hunk) == 2 and "DRM_BUS_FLAG_PIXDATA_DRIVE_NEGEDGE" in vop_hunk[1], "VOP edge not from bus flags"
assert "-\t\tVOP_REG_SET(vop, output, rgb_dclk_pol, 1);" in patch, "hard-coded edge not removed"
assert "+\ts->bus_flags = info->bus_flags;" in patch, "rockchip_rgb does not pass bus flags"

dts = (device / "linux/dts/rockchip/rk3128-powkiddy-a12-rev-a.dts").read_text()
backlight = re.search(r"backlight: backlight \{(.*?)\n\t\};", dts, re.S)
assert backlight, "backlight node missing"
body = backlight[1]
assert re.search(r"brightness-levels = <0 255>;", body), "backlight curve not linear"
assert re.search(r"num-interpolated-steps = <255>;", body)
assert re.search(r"default-brightness-level = <200>;", body), "default differs from KNULLI's 200/255"
print("display config: ok")
