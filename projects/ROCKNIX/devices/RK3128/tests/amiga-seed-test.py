#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""022-a12-bios seeds what Amiga WHDLoad games need (test 83, 2026-10-29).

WHDLoad reads KickEmu's .RTB files from whdcommon:, uae4arm's name for the
BIOS folder; uae4arm unpacks them only into roms/amiga/WHDLoad on its first
run, so Another World stopped with "DOS-Error #205 on reading
whdcommon:kick34005.a500.rtb". The boot step copies them next to the
Kickstarts. Another World's second button opens the level-code screen
(WHDLoad 2.4), so its remap puts that button on Up (jump). Files the owner
already has are left alone.
"""
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls"
script = pkg / "sources/022-a12-bios"
remap = pkg / "sources/remaps/uae4arm/AnotherWorld_v2.4_0425.rmp"
assert remap.read_text() == 'input_player1_btn_a = "4"\n', "RetroPad A (printed B) -> Up"
assert "remaps" in (pkg / "package.mk").read_text(), "the package installs the remaps"

with tempfile.TemporaryDirectory() as tmp:
    t = pathlib.Path(tmp)
    (t / "storage/roms/bios").mkdir(parents=True)
    kick = t / "storage/roms/amiga/WHDLoad/Devs/Kickstarts"
    kick.mkdir(parents=True)
    (kick / "kick34005.A500.RTB").write_text("rtb")
    (kick / "kick40063.A600.RTB").write_text("rtb2")
    (t / "storage/roms/bios/kick40063.A600.RTB").write_text("owner")
    share = t / "usr/share/a12-remaps/uae4arm"
    share.mkdir(parents=True)
    (share / remap.name).write_text(remap.read_text())
    subprocess.run(["bash", str(script)], env={"A12_ROOT": tmp, "PATH": "/usr/bin:/bin"}, check=True)
    assert (t / "storage/roms/bios/kick34005.A500.RTB").read_text() == "rtb"
    assert (t / "storage/roms/bios/kick40063.A600.RTB").read_text() == "owner", "existing file kept"
    seeded = t / "storage/remappings/uae4arm" / remap.name
    assert seeded.read_text() == remap.read_text()
    seeded.write_text("owner remap")
    subprocess.run(["bash", str(script)], env={"A12_ROOT": tmp, "PATH": "/usr/bin:/bin"}, check=True)
    assert seeded.read_text() == "owner remap", "the owner's remap is kept"
print("amiga seed: ok")
