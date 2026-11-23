#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-deploy resumes a partial upload and only reboots after a verified copy."""
import hashlib
import os
import pathlib
import subprocess
import tempfile

tool = pathlib.Path(__file__).resolve().parents[1] / "tools/a12-deploy"
with tempfile.TemporaryDirectory(prefix="a12-deploy-") as temporary:
    root = pathlib.Path(temporary)
    flash, storage = root / "flash", root / "storage"
    for path in ("extlinux", "device_trees"):
        (flash / path).mkdir(parents=True)
    for name in ("KERNEL", "KERNEL.md5", "SYSTEM", "SYSTEM.md5", "extlinux/extlinux.conf",
                 "device_trees/rk3128-powkiddy-a12-rev-a.dtb"):
        (flash / name).write_text(name)
    (storage / ".update").mkdir(parents=True)
    tar = root / "ROCKNIX-RK3128.arm-test.tar"
    payload = os.urandom(300000)
    tar.write_bytes(payload)
    # An earlier attempt died after 123456 bytes.
    (storage / ".update" / (tar.name + ".part")).write_bytes(payload[:123456])
    log = root / "commands"
    fake = root / "fake-ssh"
    fake.write_text('#!/bin/bash\ncmd="$*"\necho "$cmd" >> "%s"\ncmd=${cmd//\\/storage/%s}\ncmd=${cmd//\\/flash/%s}\n'
                    'cmd=${cmd//reboot/true}\nexec bash -c "$cmd"\n' % (log, storage, flash))
    fake.chmod(0o755)
    env = dict(os.environ, A12_SSH=str(fake), A12_HOST="192.0.2.1")
    subprocess.run(["bash", str(tool), str(tar)], env=env, check=True)
    final = storage / ".update" / tar.name
    assert final.exists() and hashlib.sha256(final.read_bytes()).digest() == hashlib.sha256(payload).digest(), "not resumed intact"
    commands = log.read_text()
    assert "tail -c" not in commands  # resume offset is applied on the host side
    assert commands.strip().splitlines()[-1].endswith("reboot"), commands
    assert not (storage / ".update" / (tar.name + ".part")).exists()

    # A corrupted upload must not be renamed into place or reboot the device.
    log.unlink()
    (storage / ".update" / tar.name).unlink()
    (storage / ".update" / (tar.name + ".part")).write_bytes(b"garbage" + payload[7:200000])
    result = subprocess.run(["bash", str(tool), str(tar)], env=env, capture_output=True, text=True)
    assert result.returncode != 0, "corrupt resume accepted"
    assert not (storage / ".update" / tar.name).exists()
    assert "reboot" not in log.read_text().splitlines()[-1]

    # Gentle mode: no on-device backup copy and a throttled upload still arrive intact.
    log.unlink()
    for leftover in (storage / ".update").iterdir():
        leftover.unlink()
    (storage / ".a12-rollback").mkdir(exist_ok=True)
    before = sorted(p.name for p in (storage / ".a12-rollback").iterdir())
    env_gentle = dict(env, A12_DEPLOY_RATE_KBPS="4096")
    subprocess.run(["bash", str(tool), "--skip-backup", str(tar)], env=env_gentle, check=True)
    assert hashlib.sha256((storage / ".update" / tar.name).read_bytes()).digest() == hashlib.sha256(payload).digest()
    assert sorted(p.name for p in (storage / ".a12-rollback").iterdir()) == before, "backup taken despite --skip-backup"
    assert "cp /flash/KERNEL" not in log.read_text()
print("deploy resume: ok")
