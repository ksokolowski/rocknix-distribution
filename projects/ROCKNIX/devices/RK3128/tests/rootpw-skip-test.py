#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""007-rootpw re-applies the root password only when something changed.

Boot timing (TEST_LOG, boot splash plan Task 10): setrootpass re-hashed the
password, re-added it to Samba and regenerated Syncthing credentials on
every boot (≈3 s on the A12) although /etc/shadow persists on /storage.
"""
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
script = (root / "projects/ROCKNIX/packages/rocknix/autostart/007-rootpw").read_text()

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    cache = tmp / "cache"
    (cache / "samba").mkdir(parents=True)
    (cache / "samba/smbpasswd").write_text("")
    (cache / "shadow").write_text("root:$6$old$hash:19000::::::\n")
    calls = tmp / "calls"
    (tmp / "functions").write_text(
        'tocon() { :; }\nget_setting() { cat "$TMP/password"; }\n')
    bindir = tmp / "bin"
    bindir.mkdir()
    (bindir / "setrootpass").write_text(
        '#!/bin/sh\necho "$1" >> "$TMP/calls"\n'
        'sed -i "s#^root:[^:]*:#root:\\$6\\$new$(date +%N)\\$h:#" "$TMP/cache/shadow"\n'
        'echo "root:1:x" > "$TMP/cache/samba/smbpasswd"\n')
    (bindir / "setrootpass").chmod(0o755)
    body = script.replace("/etc/profile.d/001-functions", str(tmp / "functions")) \
                 .replace("/storage/.cache", str(cache))
    env = dict(os.environ, TMP=str(tmp), PATH=f"{bindir}:/usr/bin:/bin")

    def boot():
        subprocess.run(["sh", "-c", body], env=env, check=True)
        return calls.read_text().split() if calls.exists() else []

    (tmp / "password").write_text("rocknix\n")
    assert boot() == ["rocknix"], "first boot must apply the password"
    assert boot() == ["rocknix"], "unchanged password must not be re-applied"
    (tmp / "password").write_text("newpass\n")
    assert boot() == ["rocknix", "newpass"], "a changed password must be applied"
    (cache / "shadow").write_text("root:$6$reset$x:19000::::::\n")
    assert boot() == ["rocknix", "newpass", "newpass"], "a reset shadow must be re-applied"
    (cache / "samba/smbpasswd").write_text("")
    assert len(boot()) == 4, "a reset Samba password file must be re-applied"
    (cache / "samba/smbpasswd").write_text("root:2:x\n")   # same size, other content
    assert len(boot()) == 5, "a changed Samba password file must be re-applied"
    assert len(boot()) == 5, "unchanged state after re-applying must be skipped"

    # On the A12, smbpasswd -sa stores root in Samba's own passdb, and
    # /storage/.cache/samba/smbpasswd stays empty (boot e590a6f8): that is a
    # successful apply and must not be re-run on every boot.
    (bindir / "setrootpass").write_text(
        '#!/bin/sh\necho "$1" >> "$TMP/calls"\n'
        'sed -i "s#^root:[^:]*:#root:\\$6\\$a12$(date +%N)\\$h:#" "$TMP/cache/shadow"\n'
        ': > "$TMP/cache/samba/smbpasswd"\n')
    (tmp / "password").write_text("a12\n")
    assert len(boot()) == 6 and (cache / "rootpass.applied").exists(), \
        "an apply that leaves the Samba file empty is still applied"
    assert len(boot()) == 6, "and is not re-applied on the next boot"
    # An empty shadow hash (no password) does not count as applied.
    (bindir / "setrootpass").write_text(
        '#!/bin/sh\necho "$1" >> "$TMP/calls"\n'
        'sed -i "s#^root:[^:]*:#root::#" "$TMP/cache/shadow"\n')
    (tmp / "password").write_text("broken\n")
    assert len(boot()) == 7 and not (cache / "rootpass.applied").exists(), \
        "a failed apply must not write the marker"
    assert len(boot()) == 8, "a failed apply must be retried"

# setrootpass must not blank the hash when cryptpw fails.
setroot = (root / "projects/ROCKNIX/packages/rocknix/sources/scripts/setrootpass").read_text()
assert 'if [ -n "${NEW}" ]; then\n  sed -i "s#root:${CURRENT}' in setroot
print("rootpw skip: ok")
