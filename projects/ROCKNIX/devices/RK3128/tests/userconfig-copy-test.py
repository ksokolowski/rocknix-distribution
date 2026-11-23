#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""A card's first boot copies only the configuration that is used (sync12).

userconfig-setup copies /usr/config into /storage/.config on a card's first
boot. On the A12 (sync11) that took 3.5 min, mostly ScummVM's themes
(73 MB) and PortMaster.zip (23 MB). Nothing reads those copies:
start_scummvm.sh passes --themepath=/usr/config/scummvm/themes, and
start_portmaster.sh and factoryreset unzip /usr/config/PortMaster/release.
So the copy leaves them out; everything else is still copied.
The script runs with its paths moved into a temporary directory.
"""
import os
import pathlib
import shutil
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
setup = root / "projects/ROCKNIX/packages/sysutils/systemd/scripts/userconfig-setup"
pkgs = root / "projects/ROCKNIX/packages"

# The premise: the programs read the image's copies, not /storage's.
assert "--themepath=/usr/config/scummvm/themes" in (pkgs / "emulators/standalone/scummvm-sa/scripts/start_scummvm.sh").read_text()
assert "unzip /usr/config/PortMaster/release/PortMaster.zip" in (pkgs / "apps/portmaster/scripts/start_portmaster.sh").read_text()

if not shutil.which("rsync"):
    print("userconfig copy: SKIP (no rsync)")
    raise SystemExit(0)

with tempfile.TemporaryDirectory() as tmp:
    t = pathlib.Path(tmp)
    cfg = t / "usr/config"
    for f in ("scummvm/scummvm.ini", "scummvm/themes/scummmodern.zip", "PortMaster/control.txt",
              "PortMaster/release/PortMaster.zip", "emulationstation/es_settings.cfg",
              "emulationstation/es_systems.cfg", "retroarch/retroarch.cfg"):
        (cfg / f).parent.mkdir(parents=True, exist_ok=True)
        (cfg / f).write_text(f)
    for d in ("storage/.config", "storage/.cache", "storage/.ssh", "bin", "var/log"):
        (t / d).mkdir(parents=True, exist_ok=True)
    (t / "bin/ldconfig").write_text("#!/bin/sh\n")
    (t / "bin/ldconfig").chmod(0o755)
    script = setup.read_text().replace(". /etc/profile.d/001-functions", "tocon() { :; }")
    script = script.replace("/usr/config", str(cfg)).replace("/storage", str(t / "storage")).replace("/var/log", str(t / "var/log"))
    script = script.replace("/usr/bin/emulationstation", str(t / "none")).replace("/usr/lib/autostart", str(t / "none"))
    (t / "setup").write_text(script)
    env = dict(os.environ, PATH=f"{t / 'bin'}:{os.environ['PATH']}")
    subprocess.run(["bash", str(t / "setup")], env=env, check=True)

    out = t / "storage/.config"
    assert (out / "scummvm/scummvm.ini").exists() and (out / "PortMaster/control.txt").exists()
    assert (out / "retroarch/retroarch.cfg").exists() and (out / "emulationstation/es_settings.cfg").exists()
    assert not (out / "emulationstation/es_systems.cfg").exists(), "es_systems.cfg is linked, not copied"
    assert not (out / "scummvm/themes").exists(), "ScummVM's themes are read from /usr/config"
    assert not (out / "PortMaster/release").exists(), "PortMaster.zip is read from /usr/config"
    assert (t / "storage/.configured").exists()

print("userconfig copy: ok")
