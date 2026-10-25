#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 hides ES's ZRAM SWAP menu (A12 ES patch 0003, owner 2026-10-17).

The menu (ES sync 2026-10-17) knows only lz4/zstd and 50-150 % sizes. The
A12's measured setup is lzo-rle with zstd recompression of idle pages at
256 MB (B9, test 41): the menu shows its zstd switch off and its size as
100 %, and any change replaces the tuning with lz4 at a percentage size.
The entry is compiled out on RK3128 only (ES builds with -D$DEVICE).
"""
import pathlib
import re
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = (root / "projects/ROCKNIX/packages/ui/emulationstation/package.mk").read_text()
version = re.search(r'^PKG_VERSION="([0-9a-f]+)"', pkg, re.M)[1]
tarball = root / f"sources/emulationstation/emulationstation-{version}.tar.gz"
patch = root / "projects/ROCKNIX/devices/RK3128/patches/emulationstation/0003-menu-hide-zram-swap-on-rk3128.patch"
src = "es-app/src/guis/GuiMenu.cpp"

assert patch.exists(), f"{patch.name} missing"
if not tarball.exists():
    print("note: ES source tarball not downloaded; ZRAM menu patch check skipped")
    raise SystemExit(0)

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    with tarfile.open(tarball) as tar:
        m = next(m for m in tar.getmembers() if m.name.endswith("/" + src))
        m.name = src
        tar.extract(m, tmp, filter="data")
    subprocess.run(["patch", "-p1", "-s", "-d", str(tmp)], input=patch.read_text(encoding="latin-1"),
                   text=True, encoding="latin-1", check=True)
    code = (tmp / src).read_text(encoding="latin-1")
    guarded = re.search(r"#if !defined\(RK3128\)\n[^#]*s->addEntry\(_\(\"ZRAM SWAP\"\)[^\n]*\n#endif", code)
    assert guarded, "ZRAM SWAP entry is not guarded for RK3128"
    assert code.count('_("ZRAM SWAP"), true') == 1
print("es zram menu: ok")
