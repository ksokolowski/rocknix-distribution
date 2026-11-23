#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Every ELF in the image finds its shared libraries (2026-10-29).

scummvm-sa was built on 2026-10-04 and linked libvpx.so.8 and libmpeg2.so.0,
which configure found in the sysroot but the package did not depend on. The
libvpx bump to 1.16 (libvpx.so.12) did not rebuild it, libmpeg2 was never in
the image, and the A12's scummvm failed to start ("libvpx.so.8: cannot open
shared object file"). The package now lists the libraries its binary links.
The image part runs when build.ROCKNIX-RK3128.arm/image/system exists.
"""
import pathlib
import re
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
mk = (root / "projects/ROCKNIX/packages/emulators/standalone/scummvm-sa/package.mk").read_text()
deps = re.search(r'^PKG_DEPENDS_TARGET="([^"]*)"', mk, re.M)[1].split()
for lib in ("libvpx", "libmpeg2", "libvorbis", "libogg", "libjpeg-turbo", "libpng", "zlib", "curl"):
    assert lib in deps, f"scummvm-sa links {lib} but does not depend on it"

# Known gaps outside this fix, each tracked in BACKLOG.
KNOWN = {("usr/lib/libmoonlight-rk.so", "librockchip_mpp.so.1")}

system = root / "build.ROCKNIX-RK3128.arm/image/system"
if not system.is_dir():
    print("image sonames: ok (SKIP image: not built)")
    raise SystemExit(0)
have = {p.name for p in system.rglob("*.so*")}
missing = []
for f in system.rglob("*"):
    if not f.is_file() or f.is_symlink():
        continue
    with f.open("rb") as h:
        if h.read(4) != b"\x7fELF":
            continue
    out = subprocess.run(["readelf", "-d", str(f)], capture_output=True, text=True).stdout
    for name in re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", out):
        rel = str(f.relative_to(system))
        if name not in have and (rel, name) not in KNOWN:
            missing.append(f"{rel} -> {name}")
assert not missing, "missing shared libraries:\n" + "\n".join(sorted(missing))
print("image sonames: ok")
