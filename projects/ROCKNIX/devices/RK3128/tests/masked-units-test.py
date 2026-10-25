#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 image masks services the owner does not want (test 44).

Telemetry (rocknix-report-stats posts to stats.rocknix.org), the root
debug shell on tty9 (no keyboard on the A12), rpcbind (NFS) and avahi
(mDNS; Samba is off). Masks are /etc/systemd/system links to /dev/null
shipped in the read-only image by a12-controls. systemd-oomd, enabled by
upstream in 2026-10, stays masked until it is measured on the A12.
"""
import pathlib
import re

root = pathlib.Path(__file__).resolve().parents[5]
mk = (root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/package.mk").read_text()
units = set(re.search(r"A12_MASKED_UNITS=\"([^\"]+)\"", mk)[1].split())
assert units == {"rocknix-report-stats.timer", "rocknix-report-stats.service", "debug-shell.service",
                 "rpcbind.service", "rpcbind.socket", "avahi-daemon.service", "avahi-daemon.socket",
                 "systemd-oomd.service", "systemd-oomd.socket"}, units
# Upstream still ships and enables oomd; the mask must name its real units.
systemd = (root / "projects/ROCKNIX/packages/sysutils/systemd/package.mk").read_text()
assert "enable_service systemd-oomd.socket" in systemd and "enable_service systemd-oomd.service" in systemd
assert re.search(r'for unit in \$\{A12_MASKED_UNITS\}; do\n\s+ln -sf /dev/null "\$\{INSTALL\}/etc/systemd/system/\$\{unit\}"', mk)
assert "a12-controls" not in units and "sshd.service" not in units
print("masked units: ok")
