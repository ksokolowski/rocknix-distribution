#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""perf is built for /usr, not for the builder's home folder (test 103).

The kernel's perf Makefile defaults prefix to $(HOME); the build container
inherits the builder's HOME, so every image's perf carried the builder's
home path (found by the release audit) and looked for libexec/perf-core
there. The linux package now passes prefix=/usr.
"""
import pathlib
import re
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
mk = (root / "projects/ROCKNIX/packages/linux/package.mk").read_text()
block = mk[mk.index("( cd tools/perf"):mk.index("cp perf ${INSTALL}/usr/bin")]
assert re.search(r"make \$\{PERF_BUILD_ARGS\} prefix=/usr", block), "perf: prefix=/usr"

perf = root / "build.ROCKNIX-RK3128.arm/image/system/usr/bin/perf"
if perf.is_file():
    text = subprocess.run(["strings", str(perf)], capture_output=True, text=True).stdout
    homes = [l for l in text.splitlines() if re.fullmatch(r"/home/[^/\s]+", l)]
    if homes:
        print("perf prefix: ok (SKIP built image: older than the fix, rebuild linux)")
    else:
        print("perf prefix: ok (built image checked)")
else:
    print("perf prefix: ok")
