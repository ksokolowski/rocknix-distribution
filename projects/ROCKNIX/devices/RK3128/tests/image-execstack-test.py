#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""No shared library in the image asks for an executable stack (2026-11-11).

glibc 2.44 refuses to dlopen a library with GNU_STACK RWE into a process
whose stack is not executable. RetroArch used to be RWE itself, so cores
with ARM assembly lacking `.note.GNU-stack` (FBNeo's Cyclone, uae4arm,
PicoDrive) still loaded. With upstream 2026-11-11 RetroArch is RW, and on
sync25 every FBNeo and Amiga game failed: "cannot enable executable stack
as shared object requires: Invalid argument". The assembly does not run code
on the stack; the cores, and libmpeg2 (ScummVM), link with -z noexecstack on
32-bit ARM. The image
part runs when build.ROCKNIX-RK3128.arm/image/system exists.
"""
import pathlib
import re
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
libretro = root / "projects/ROCKNIX/packages/emulators/libretro"
for mk in [libretro / c / "package.mk" for c in ("fbneo-lr", "uae4arm-lr", "picodrive-lr")] + \
          [root / "packages/multimedia/libmpeg2/package.mk"]:
    assert "-z,noexecstack" in mk.read_text(), f"{mk.parent.name} links with -z noexecstack"

system = root / "build.ROCKNIX-RK3128.arm/image/system"
if not system.is_dir():
    print("image execstack: ok (SKIP image: not built)")
    raise SystemExit(0)
rwe = []
for f in system.rglob("*.so*"):
    if not f.is_file() or f.is_symlink():
        continue
    with f.open("rb") as h:
        if h.read(4) != b"\x7fELF":
            continue
    out = subprocess.run(["readelf", "-lW", str(f)], capture_output=True, text=True).stdout
    if re.search(r"GNU_STACK.*RWE", out):
        rwe.append(str(f.relative_to(system)))
assert not rwe, "shared objects with an executable stack:\n" + "\n".join(sorted(rwe))
print("image execstack: ok")
