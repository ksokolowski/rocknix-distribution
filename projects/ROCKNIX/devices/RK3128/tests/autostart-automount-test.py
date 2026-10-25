#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""B2: on the A12, automount runs alongside the common autostart scripts.

Test 48 left "start automount without blocking autostart" as a boot-time
candidate (automount took about 1.3 s). automount bind-mounts the games
directories over /storage/roms, so nothing may write there before it ends:
the common scripts do not use /storage/roms (checked below, so a future
upstream script that does fails this test), and autostart waits for the
automount job before the device and custom scripts (the owner's PortMaster
script writes to roms/ports). Other devices keep the blocking start.
"""
import os
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
script = (root / "projects/ROCKNIX/packages/sysutils/autostart/sources/autostart").read_text()


def boot(device):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        log = tmp / "order"
        bindir = tmp / "bin"
        bindir.mkdir()
        for name, body in {"systemctl": f'echo "systemctl $*" >> {log}',
                           "performance": "exit 0", "tocon": "exit 0", "clear": "exit 0",
                           "get_setting": "exit 0"}.items():
            (bindir / name).write_text(f"#!/bin/sh\n{body}\n")
            (bindir / name).chmod(0o755)
        lib = tmp / "lib"
        for d, name in (("common", "050-common"), (device, "060-device")):
            (lib / d).mkdir(parents=True, exist_ok=True)
            (lib / d / name).write_text(f"#!/bin/sh\necho 'run {name}' >> {log}\n")
            (lib / d / name).chmod(0o755)
        custom = tmp / "custom"
        custom.mkdir()
        (custom / "099-custom").write_text(f"#!/bin/sh\necho 'run 099-custom' >> {log}\n")
        (custom / "099-custom").chmod(0o755)
        (tmp / "os-release").write_text("")
        (tmp / "profile").write_text("")
        (tmp / "start.games").write_text("")
        body = (script.replace("/etc/os-release", str(tmp / "os-release"))
                      .replace("/etc/profile", str(tmp / "profile"))
                      .replace("/usr/lib/autostart", str(lib))
                      .replace("/storage/.config/autostart", str(custom))
                      .replace("/var/log/boot.log", str(tmp / "boot.log"))
                      .replace("/run/rocknix/start.games", str(tmp / "start.games"))
                      .replace(">/dev/console", ">/dev/null"))
        env = dict(os.environ, PATH=f"{bindir}:/usr/bin:/bin", HW_DEVICE=device, UI_SERVICE="emustation")
        subprocess.run(["bash", "-c", body], env=env, check=True)
        return [l for l in log.read_text().splitlines() if "emustation" not in l]


assert boot("RK3128") == ["systemctl start --no-block rocknix-automount", "run 050-common",
                          "systemctl start rocknix-automount", "run 060-device", "run 099-custom"]
assert boot("RK3326") == ["systemctl start rocknix-automount", "run 050-common",
                          "run 060-device", "run 099-custom"]

# Common scripts that reach the A12 image must not touch the games mounts.
common = [root / "projects/ROCKNIX/packages/rocknix/autostart",
          root / "projects/ROCKNIX/packages/sysutils/system-utils/sources/autostart/common",
          root / "projects/ROCKNIX/packages/virtual/emulators/autostart",
          root / "projects/ROCKNIX/packages/hardware/quirks/autostart"]
files = [f for d in common for f in d.iterdir()]
files.append(root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/sources/021-a12-tools")
assert len(files) > 10, files
for f in files:
    text = f.read_text(errors="replace")
    assert not re.search(r"/storage/roms|/storage/games|games-(in|ex)ternal|automount", text), f
print("autostart automount: ok")
