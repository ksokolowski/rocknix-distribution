#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Keepalive pings the gateway and configured peers, ignoring bad entries."""
import os
import pathlib
import subprocess
import tempfile

script = pathlib.Path(__file__).resolve().parents[1] / "packages/a12-controls/sources/a12-neighbor-keepalive"

with tempfile.TemporaryDirectory(prefix="a12-keepalive-") as temporary:
    directory = pathlib.Path(temporary)
    log = directory / "pings"
    (directory / "ping").write_text('#!/bin/sh\nfor last; do :; done\necho "$last" >> "%s"\n[ "$last" != 192.0.2.9 ]\n' % log)
    (directory / "ip").write_text('#!/bin/sh\necho "default via 192.0.2.1 dev wlan0"\n')
    (directory / "logger").write_text('#!/bin/sh\nexit 0\n')
    for name in ("ping", "ip", "logger"):
        (directory / name).chmod(0o755)
    config = directory / "a12-keepalive.conf"
    config.write_text('HOSTS="192.0.2.5 not-an-ip;reboot 192.0.2.9"\n')
    environment = dict(os.environ, PATH=f"{directory}:/usr/bin:/bin", A12_KEEPALIVE_CONFIG=str(config))
    result = subprocess.run(["sh", str(script)], env=environment)
    assert result.returncode == 0, result.returncode
    assert log.read_text().split() == ["192.0.2.1", "192.0.2.5", "192.0.2.9"], log.read_text()

    log.unlink()
    config.unlink()
    result = subprocess.run(["sh", str(script)], env=environment)
    assert result.returncode == 0
    assert log.read_text().split() == ["192.0.2.1"]
print("neighbor keepalive: ok")
