#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-wifi-provision captures saved Wi-Fi over SSH and seeds a STORAGE mount."""
import os
import pathlib
import stat
import subprocess
import tempfile

tool = pathlib.Path(__file__).resolve().parents[1] / "tools/a12-wifi-provision"
files = {".config/NetworkManager/system-connections/Lab.nmconnection": "[wifi]\nssid=Lab\n",
         ".cache/iwd/Lab.psk": "[Security]\nPassphrase=secret\n",
         ".config/a12-keepalive.conf": 'HOSTS="192.0.2.24"\n'}

with tempfile.TemporaryDirectory(prefix="a12-wifi-") as temporary:
    root = pathlib.Path(temporary)
    device = root / "device-storage"
    for name, body in files.items():
        (device / name).parent.mkdir(parents=True, exist_ok=True)
        (device / name).write_text(body)
    # Fake a12-ssh: run the remote command locally with /storage mapped to the fake device.
    fake_ssh = root / "fake-ssh"
    fake_ssh.write_text('#!/bin/sh\ncd "%s" && sh -c "$(printf %%s "$*" | sed "s#/storage#.#g")"\n' % device)
    fake_ssh.chmod(0o755)
    saved = root / "saved"
    env = dict(os.environ, A12_SSH=str(fake_ssh))
    subprocess.run(["bash", str(tool), "capture", str(saved)], env=env, check=True)
    assert stat.S_IMODE(saved.stat().st_mode) == 0o700, oct(saved.stat().st_mode)
    for name, body in files.items():
        assert (saved / name).read_text() == body, name

    storage = root / "card-storage"
    storage.mkdir()
    subprocess.run(["bash", str(tool), "install", str(storage), str(saved)], env=env, check=True)
    for name, body in files.items():
        target = storage / name
        assert target.read_text() == body, name
        assert stat.S_IMODE(target.stat().st_mode) == 0o600, (name, oct(target.stat().st_mode))

    empty = root / "empty"
    empty.mkdir()
    result = subprocess.run(["bash", str(tool), "install", str(storage), str(empty)], env=env, capture_output=True)
    assert result.returncode != 0, "install from an empty capture must fail"
print("wifi provision: ok")
