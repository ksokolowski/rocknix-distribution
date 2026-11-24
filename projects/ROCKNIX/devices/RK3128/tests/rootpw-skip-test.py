#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""setrootpass re-applies the root password only when something changed.

Boot timing (TEST_LOG, boot splash plan Task 10): setrootpass re-hashed the
password, re-added it to Samba and regenerated Syncthing credentials on
every boot (≈3 s on the A12) although /etc/shadow persists on /storage.
The check lives in setrootpass itself (ROCKNIX review of #3561), so
007-rootpw and ES's password change both go through it. It counts as
applied only when shadow holds the hash it just made, so a failed cryptpw
is retried on the next call.
"""
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
setroot = (root / "projects/ROCKNIX/packages/rocknix/sources/scripts/setrootpass").read_text()
hook = (root / "projects/ROCKNIX/packages/rocknix/autostart/007-rootpw").read_text()
assert 'setrootpass "${ROOTPASS}"' in hook and "rootpass.applied" not in hook, \
    "007-rootpw calls setrootpass; the check is in setrootpass"

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    cache = tmp / "cache"
    (cache / "samba").mkdir(parents=True)
    (cache / "samba/smbpasswd").write_text("")
    (cache / "shadow").write_text("root:$6$old$hash:19000::::::\n")
    calls = tmp / "calls"
    (tmp / "profile").write_text('get_setting() { :; }\nset_setting() { :; }\n')
    bindir = tmp / "bin"
    bindir.mkdir()

    def tool(name, body):
        (bindir / name).write_text("#!/bin/sh\n" + body)
        (bindir / name).chmod(0o755)

    # cryptpw -m sha512 PASSWORD prints a new hash each call and logs PASSWORD;
    # smbpasswd writes the Samba file as $SMB says.
    tool("cryptpw", '[ -n "$FAILHASH" ] && exit 1; echo "$3" >> "$TMP/calls"; echo "\\$6\\$n$(date +%N)\\$h"\n')
    tool("smbpasswd", 'cat >/dev/null; [ "$SMB" = empty ] && : > "$TMP/cache/samba/smbpasswd" || echo "root:1:x" > "$TMP/cache/samba/smbpasswd"\n')
    tool("syncthing", ":\n")
    tool("systemctl", ":\n")
    body = setroot.replace(". /etc/profile", f". {tmp / 'profile'}").replace("/storage/.cache", str(cache))
    script = tmp / "setrootpass"
    script.write_text(body)

    def apply(password, **env_extra):
        env = dict(os.environ, TMP=str(tmp), PATH=f"{bindir}:/usr/bin:/bin", **env_extra)
        subprocess.run(["bash", str(script), password], env=env, check=True)
        return calls.read_text().split() if calls.exists() else []

    assert apply("rocknix") == ["rocknix"], "first boot must apply the password"
    assert apply("rocknix") == ["rocknix"], "unchanged password must not be re-applied"
    assert apply("newpass") == ["rocknix", "newpass"], "a changed password must be applied"
    (cache / "shadow").write_text("root:$6$reset$x:19000::::::\n")
    assert apply("newpass") == ["rocknix", "newpass", "newpass"], "a reset shadow must be re-applied"
    (cache / "samba/smbpasswd").write_text("")
    assert len(apply("newpass")) == 4, "a reset Samba password file must be re-applied"
    (cache / "samba/smbpasswd").write_text("root:2:x\n")   # same size, other content
    assert len(apply("newpass")) == 5, "a changed Samba password file must be re-applied"
    assert len(apply("newpass")) == 5, "unchanged state after re-applying must be skipped"

    # On the A12, smbpasswd -sa stores root in Samba's own passdb, and
    # /storage/.cache/samba/smbpasswd stays empty (boot e590a6f8): that is a
    # successful apply and must not be re-run on every boot.
    assert len(apply("a12", SMB="empty")) == 6 and (cache / "rootpass.applied").exists(), \
        "an apply that leaves the Samba file empty is still applied"
    assert len(apply("a12", SMB="empty")) == 6, "and is not re-applied on the next boot"

    # cryptpw fails: the old hash stays (never an empty one) and the new
    # password is not applied, so it must not count as applied.
    before = (cache / "shadow").read_text()
    apply("broken", FAILHASH="1")
    assert (cache / "shadow").read_text() == before, "a failed cryptpw must leave the old hash"
    assert not (cache / "rootpass.applied").exists(), "a failed apply must not write the marker"
    assert len(apply("broken")) == 7, "a failed apply must be retried"
    assert len(apply("broken")) == 7, "and skipped once it succeeded"

print("rootpw skip: ok")
