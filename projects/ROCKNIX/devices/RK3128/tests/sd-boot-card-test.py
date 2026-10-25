#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The boot SD card holds the root filesystem, so it must never be treated as removed.

Test 22's panic: under heavy Wi-Fi traffic the broken-cd presence poll failed,
the core detached the card under a mounted SquashFS and the re-attach oopsed.
"""
import pathlib
import re

dts = (pathlib.Path(__file__).resolve().parents[1] / "linux/dts/rockchip/rk3128-powkiddy-a12-rev-a.dts").read_text()
node = re.search(r"&sdmmc\s*{(.*?)\n};", dts, re.S)
assert node, "&sdmmc override missing"
body = node[1]
assert re.search(r"^\s*non-removable;", body, re.M), "boot card not non-removable"
assert not re.search(r"^\s*broken-cd;", body, re.M), "broken-cd polling still enabled"
print("sd boot card: ok")
