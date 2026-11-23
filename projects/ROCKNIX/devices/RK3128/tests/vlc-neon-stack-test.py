#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""VLC's ARM assembly does not ask for an executable stack (A12 patch 0002).

glibc 2.41+ refuses to dlopen() a library marked GNU_STACK RWE, and none of
VLC's hand-written ARM files had a .note.GNU-stack section, so on the A12
the NEON chroma/volume/channel mixer plugins and the deinterlace filter
never loaded (cvlc -vv: "cannot enable executable stack"). The patch adds
the note to asm.S, which every one of them includes. With the pinned
tarball and an ARM cross compiler, each file is assembled and linked into
a shared object, which must come out GNU_STACK RW.
"""
import pathlib
import re
import shutil
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = (root / "projects/ROCKNIX/packages/multimedia/vlc/package.mk").read_text()
version = re.search(r'^PKG_VERSION="([^"]+)"', pkg, re.M)[1]
tarball = root / f"sources/vlc/vlc-{version}.tar.xz"
patch = root / "projects/ROCKNIX/devices/RK3128/patches/vlc/0002-arm_neon-mark-the-assembly-stack-non-executable.patch"

text = patch.read_text()
assert '.pushsection .note.GNU-stack,"",%progbits' in text and "#ifdef __ELF__" in text

if not tarball.exists():
    print("note: VLC source tarball not downloaded; assembly stack check skipped")
    raise SystemExit(0)

cc = shutil.which("arm-linux-gnueabihf-gcc")
with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    with tarfile.open(tarball) as tar:
        members = [m for m in tar.getmembers() if m.name.endswith(".S")]
        for m in members:
            m.name = m.name.split("/", 1)[1]
            tar.extract(m, tmp, filter="data")
    subprocess.run(["patch", "-p1", "-s", "-d", str(tmp)], input=text, text=True, check=True)
    sources = sorted(p for p in tmp.rglob("*.S") if "arm64" not in p.name and p.name != "asm.S")
    assert sources and all('#include "' in p.read_text() and "asm.S" in p.read_text() for p in sources), \
        "every ARM assembly file must include asm.S"
    if cc is None:
        print("note: arm-linux-gnueabihf-gcc not installed; assembly stack check skipped")
        raise SystemExit(0)
    objs = []
    for src in sources:
        obj = tmp / (src.stem + ".o")
        subprocess.run([cc, "-march=armv7-a", "-mfpu=neon-vfpv4", "-mfloat-abi=hard",
                        "-I", str(tmp / "modules/video_filter"), "-c", str(src), "-o", str(obj)], check=True)
        sections = subprocess.run(["readelf", "-SW", str(obj)], capture_output=True, text=True, check=True).stdout
        assert ".note.GNU-stack" in sections, f"{src.name}: no .note.GNU-stack"
        objs.append(str(obj))
    so = tmp / "all.so"
    subprocess.run([cc, "-shared", "-o", str(so)] + objs, check=True)
    headers = subprocess.run(["readelf", "-lW", str(so)], capture_output=True, text=True, check=True).stdout
    stack = next(line.split() for line in headers.splitlines() if line.split()[:1] == ["GNU_STACK"])
    assert stack[-2] == "RW", stack
print(f"vlc neon stack: ok ({len(sources)} assembly files, GNU_STACK RW)")
