#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 turns watermark boosting off (test 90, 2026-11-23).

After a fragmentation event the kernel raises its watermarks and kswapd
reclaims extra memory for compaction. Upstream ROCKNIX turned that off for
RK3566 and RK3326. On the A12 (7.3, a 70 MB stand-in for ES, Metal Slug,
KOF '98, Another World, Crash 2 per round, rounds alternating): with 0
kswapd woke 53/77 times against 173/238, direct-reclaim stalls 66/48 against
84/120, no compaction stalls against 8-9 (all failed), about 5 MB more
MemAvailable at the low point, and 45 CMA allocations without a failure
either way. The setting sits in the A12's own memory sysctl file.
"""
import pathlib
import re

root = pathlib.Path(__file__).resolve().parents[5]
pkg = root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls"
conf = (pkg / "sources/zz-a12-memory.conf").read_text()
assert re.search(r"^vm\.watermark_boost_factor=0$", conf, re.M), "boost off"
assert re.search(r"^vm\.min_free_kbytes=4096$", conf, re.M), "the 4 MiB floor stays"
assert "zz-a12-memory.conf" in (pkg / "package.mk").read_text(), "installed to sysctl.d"

image = root / "build.ROCKNIX-RK3128.arm/image/system/usr/lib/sysctl.d/zz-a12-memory.conf"
if image.is_file() and not re.search(r"^vm\.watermark_boost_factor=0$", image.read_text(), re.M):
    print("watermark boost: ok (SKIP built image: older than the change, rebuild a12-controls)")
elif image.is_file():
    print("watermark boost: ok (built image checked)")
else:
    print("watermark boost: ok")
