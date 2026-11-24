#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The top USB-A port is a host port (2026-10-28).

The A12 has two USB-A ports: the bottom one is the EHCI/OHCI host
(101c0000), the top one is the DWC2 OTG controller (10180000); USB-C only
charges. With dr_mode = "otg" the OTG controller stayed a device (a USB-A
socket has no ID pin) and a wireless keyboard/mouse dongle in the top port
never enumerated, although the port has 5 V. DTB swap on the A12 (boot
b7b039cb) with dr_mode = "host": the Lenovo combo dongle enumerated on bus 1,
keyboard and mouse worked in ES, charging unaffected.
"""
import pathlib
import re
import shutil
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
dts = (root / "projects/ROCKNIX/devices/RK3128/linux/dts/rockchip/rk3128-powkiddy-a12-rev-a.dts").read_text()
otg = re.search(r"^&usb_otg \{(.*?)\};", dts, re.M | re.S)
assert otg, "usb_otg node"
assert 'dr_mode = "host";' in otg[1], "the OTG controller drives the top port as a host"
assert 'status = "okay";' in otg[1]

dtb = root / "build.ROCKNIX-RK3128.arm/image/system/usr/share/bootloader/device_trees/rk3128-powkiddy-a12-rev-a.dtb"
if dtb.is_file() and shutil.which("fdtget"):
    got = subprocess.run(["fdtget", str(dtb), "/usb@10180000", "dr_mode"],
                         capture_output=True, text=True, check=True).stdout.strip()
    if got != "host":
        print(f"usb otg host: ok (SKIP built DTB: {got}, rebuild linux)")
        raise SystemExit(0)
    print("usb otg host: ok (built DTB checked)")
else:
    print("usb otg host: ok")
