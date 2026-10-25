#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Linux drives the SD card at 50 MHz high speed (sync13).

The board tree had max-frequency = 37.5 MHz since the first port commit,
with no recorded reason; KNULLI runs these boards at 50 MHz. UHS is not
possible (vqmmc is the fixed 3.3 V vcc_io), so 50 MHz high speed is the
ceiling. Test 76 (2026-10-25), DTB swap on the A12 and the A13: raw read
15.7 -> 20.6 MiB/s (A12) and 16.4 -> 21.9 MiB/s (A13), 6 x 256 MiB written
and read back intact, no SD errors, cold power-on clean. U-Boot keeps its
own 37.5 MHz tree (mainline-uboot-test.py): it only loads the kernel.
"""
import pathlib
import re
import shutil
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
dts = (root / "projects/ROCKNIX/devices/RK3128/linux/dts/rockchip/rk3128-powkiddy-a12-rev-a.dts").read_text()
sdmmc = re.search(r"^&sdmmc \{\n(.*?)^\};", dts, re.M | re.S)[1]
assert re.search(r"^\tmax-frequency = <50000000>;", sdmmc, re.M), "the SD bus runs at 50 MHz"
assert "cap-sd-highspeed;" in sdmmc and "sd-uhs" not in sdmmc, "high speed, no UHS (fixed 3.3 V I/O)"

dtb = root / "build.ROCKNIX-RK3128.arm/image/system/usr/share/bootloader/device_trees/rk3128-powkiddy-a12-rev-a.dtb"
if dtb.is_file() and shutil.which("fdtget"):
    got = subprocess.run(["fdtget", "-t", "u", str(dtb), "/mmc@10214000", "max-frequency"],
                         capture_output=True, text=True, check=True).stdout.split()
    assert got == ["50000000"], f"built DTB: {got}"
    print("sd clock: ok (built DTB checked)")
else:
    print("sd clock: ok")
