#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 keeps rocknix-splash 81b104a (sync 2026-10-17, owner's call).

Upstream moved the pin back to 9d295bc, a commit missing from the public
history that adds an obfuscated official-build check (integrity.c, z9) and
lacks the adaptive scaling the A12 boot logo was verified with (test 61).
Other devices follow upstream's pin.
"""
import pathlib
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
pkg = root / "projects/ROCKNIX/packages/tools/rocknix-splash/package.mk"


def version(device):
    out = subprocess.run(["bash", "-c", f'DEVICE={device}; . "{pkg}"; echo "$PKG_VERSION $PKG_SHA256"'],
                         check=True, capture_output=True, text=True).stdout.split()
    return out


a12 = version("RK3128")
assert a12 == ["81b104a83c11bd3ecf5a4ce3ef1d4ed3fc5193b3",
               "31f61f2ffd7faf3baf7a881ccda2748e1c3713e20967a73aa7b85d4fc4cbd2a4"], a12
other = version("RK3326")
assert other[0] != a12[0], other
print("splash pin: ok")
