#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""021-a12-tools edits the Tools menu only when it has something to change.

It drops shortcuts whose emulator the A12 image lacks and turns the 64-bit
RetroArch entry into the native one. Each xmlstarlet start costs about
0.3 s on the A12, and the script ran it six times on every boot: 1.8 s
(test 92). 001-sync-modules restores the image's menu before it on every
boot, so the edits are needed every time: all of them go in one start, and
a menu with nothing to change gets none.
"""
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
hook = root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/sources/021-a12-tools"


def entry(script):
    return f"  <game>\n    <path>./{script}</path>\n    <name>{script}</name>\n  </game>\n"


def run(fake, gamelist_entries):
    """Run the hook on a fake card; return the xmlstarlet calls it made."""
    modules = fake / "storage/.config/modules"
    modules.mkdir(parents=True, exist_ok=True)
    (modules / "gamelist.xml").write_text("<gameList>\n" + "".join(entry(s) for s in gamelist_entries) + "</gameList>\n")
    share = fake / "usr/share/a12-controls"
    share.mkdir(parents=True, exist_ok=True)
    (share / "Start Retroarch.sh").write_text("#!/bin/sh\n")
    (fake / "usr/bin").mkdir(parents=True, exist_ok=True)
    (fake / "usr/bin/start_portmaster.sh").write_text("")
    (fake / "usr/bin/start_portmaster.sh").chmod(0o755)
    stub = fake / "stub"
    stub.mkdir(exist_ok=True)
    log = fake / "xmlstarlet.log"
    log.write_text("")
    (stub / "xmlstarlet").write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\n')
    (stub / "xmlstarlet").chmod(0o755)
    env = {"A12_ROOT": str(fake), "PATH": f"{stub}:{os.environ['PATH']}"}
    subprocess.run(["bash", str(hook)], env=env, check=True)
    assert (modules / "Start Retroarch.sh").exists(), "the native RetroArch shortcut is installed"
    return [line for line in log.read_text().splitlines() if line]


with tempfile.TemporaryDirectory() as tmp:
    fake = pathlib.Path(tmp)
    calls = run(fake, ["Start PortMaster.sh", "Start Flycast.sh", "Start 32bit Retroarch.sh",
                       "Start 64bit Retroarch.sh", "Start Retroarch.sh"])
    removed = " ".join(c for c in calls if " -d " in c)
    assert "Start Flycast.sh" in removed, f"a shortcut without its emulator goes: {calls}"
    assert "Start 32bit Retroarch.sh" in removed, calls
    assert "Start PortMaster.sh" not in removed, f"PortMaster is in the image, its shortcut stays: {calls}"
    assert any("Start 64bit Retroarch.sh" in c and " -u " in c for c in calls), f"64-bit entry renamed: {calls}"

    # 001-sync-modules copies the image's full menu back on every boot, so
    # the edits come back every time: one xmlstarlet start for all of them.
    assert len(calls) == 1, f"xmlstarlet started {len(calls)} times for one menu: {calls}"

    # A menu with nothing to change (another image): no start at all.
    calls = run(fake, ["Start PortMaster.sh", "Start Retroarch.sh"])
    assert calls == [], f"nothing to change, yet xmlstarlet ran {len(calls)} times: {calls}"

print("tools menu: ok")
