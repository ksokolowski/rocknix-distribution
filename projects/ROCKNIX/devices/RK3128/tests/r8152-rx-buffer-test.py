#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""r8152 uses 16 KiB receive buffers for an RTL8156 below SuperSpeed (test 57).

rtl8152_open() allocates RTL8152_MAX_RX (10) receive buffers of rx_buf_sz;
48 KiB is an order-4 (64 KiB) allocation, above PAGE_ALLOC_COSTLY_ORDER, so
it fails quickly on fragmented memory: on the A12's first boot after an
update NetworkManager's link-up got ENOMEM and the wired link never came up
(boots 30af22fa, 05cbf203; reproduced with fragmented memory). Upstream
already uses 16 KiB for the RTL8153 below SuperSpeed; the A12's host is
USB 2.0. Check the patch, and if A12_LINUX_SRC is set, that it applies and
leaves 48 KiB only for SuperSpeed.
"""
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

device = pathlib.Path(__file__).resolve().parents[1]
patch = device / "patches/linux/0015-r8152-use-16k-rx-buffers-for-rtl8156-below-superspeed.patch"
text = patch.read_text()
assert "drivers/net/usb/r8152.c" in text
added = [l for l in text.splitlines() if l.startswith("+") and not l.startswith("+++")]
removed = [l for l in text.splitlines() if l.startswith("-") and not l.startswith("---")]
assert sum("48 * 1024" in l for l in removed) == 2, removed
assert sum("tp->udev->speed < USB_SPEED_SUPER" in l for l in added) == 2, added

src = os.environ.get("A12_LINUX_SRC")
if not src or not (pathlib.Path(src) / "drivers/net/usb/r8152.c").exists():
    print("note: A12_LINUX_SRC not set; r8152 patch apply skipped")
    print("r8152 rx buffer: ok")
    raise SystemExit(0)
with tempfile.TemporaryDirectory() as tmp:
    dst = pathlib.Path(tmp) / "drivers/net/usb"
    dst.mkdir(parents=True)
    orig = pathlib.Path(src) / "drivers/net/usb/r8152.c"
    shutil.copy(orig, dst / "r8152.c")
    if "USB_SPEED_SUPER)\n\t\t\ttp->rx_buf_sz\t= 16 * 1024;\n\t\telse\n\t\t\ttp->rx_buf_sz\t= 48" in orig.read_text():
        code = orig.read_text()  # already patched build tree
    else:
        subprocess.run(["patch", "-p1", "-s", "-d", tmp], input=text, text=True, check=True)
        code = (dst / "r8152.c").read_text()
    cases = re.findall(r"if \(tp->udev->speed < USB_SPEED_SUPER\)\n\t+tp->rx_buf_sz\t= 16 \* 1024;\n\t+else\n\t+tp->rx_buf_sz\t= (\d+) \* 1024;", code)
    assert cases.count("48") == 2, cases
    assert not re.search(r"^\t\ttp->rx_buf_sz\t\t= 48 \* 1024;", code, re.M)
print("r8152 rx buffer: ok")
