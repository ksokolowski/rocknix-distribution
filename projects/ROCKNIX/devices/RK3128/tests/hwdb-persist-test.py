#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 keeps the udev hwdb on /storage and rebuilds it only on change.

2026-10-11: ROCKNIX rebuilt the 12.5 MB hwdb.bin into /run (tmpfs, RAM) on
every boot (5.5 s, the slowest unit). udev reads /etc/systemd/hwdb/hwdb.bin
first; the image links that directory to /storage/.cache/hwdb.
"""
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
device = root / "projects/ROCKNIX/devices/RK3128"
script = (device / "packages/a12-controls/sources/a12-hwdb-update").read_text()
dropin = (device / "packages/quirks/system.d/systemd-hwdb-update.service.d/20-a12-hwdb.conf").read_text()
mk = (device / "packages/a12-controls/package.mk").read_text()

assert "ln -sf /storage/.cache/hwdb ${INSTALL}/etc/systemd/hwdb" in mk
assert "a12-hwdb-update" in mk
for line in ("ConditionPathExists=\n", "ConditionDirectoryNotEmpty=\n", "ExecStart=\n",
             "ExecStart=/usr/bin/a12-hwdb-update\n"):
    assert line in dropin, line

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    run, store, user, bindir = tmp / "run", tmp / "store", tmp / "user", tmp / "bin"
    for d in (run, user, bindir):
        d.mkdir()
    (tmp / "os-release").write_text('BUILD_ID="abc"\n')
    count = tmp / "count"
    (bindir / "systemd-hwdb").write_text(
        f'#!/bin/sh\n[ "$1" = update ] || exit 2\necho x >> {count}\necho db > {run}/hwdb.bin\n')
    (bindir / "systemd-hwdb").chmod(0o755)
    env = dict(os.environ, PATH=f"{bindir}:/usr/bin:/bin", A12_HWDB_DIR=str(store),
               A12_HWDB_RUN=str(run), A12_HWDB_USER=str(user), A12_OS_RELEASE=str(tmp / "os-release"))

    def update():
        subprocess.run(["sh", "-c", script], env=env, check=True)
        return len(count.read_text().split()) if count.exists() else 0

    assert update() == 1 and (store / "hwdb.bin").read_text() == "db\n"
    assert not (run / "hwdb.bin").exists(), "hwdb.bin must not stay in tmpfs"
    assert update() == 1, "unchanged sources must not rebuild"
    (user / "70-custom.hwdb").write_text("evdev:x\n")
    assert update() == 2, "a user hwdb file must trigger a rebuild"
    (tmp / "os-release").write_text('BUILD_ID="def"\n')
    assert update() == 3, "a new image must trigger a rebuild"
    (store / "hwdb.bin").unlink()
    assert update() == 4, "a missing database must be rebuilt"
print("hwdb on storage: ok")
