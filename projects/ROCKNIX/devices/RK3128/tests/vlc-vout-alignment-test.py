#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""VLC keeps the private video output data naturally aligned (A12 patch 0001).

ES crashed with SIGBUS whenever it played a preview video (BACKLOG, owner
play test 2026-10-11): vout_Create() put vout_thread_sys_t at &vout[1]; on
32-bit ARM sizeof(vout_thread_t) is 28, so the condition variable
vout->p->control.wait_acknowledge sat at vout + 428 (4 mod 8) and glibc's
pthread_cond_wait() ldrexd on it faulted. spu_Create() had the same layout.
The patch must apply to the pinned VLC and replace both placements by one
allocation struct; the A12 reproduction is tools a12-vlcplay.
"""
import pathlib
import re
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = (root / "projects/ROCKNIX/packages/multimedia/vlc/package.mk").read_text()
version = re.search(r'^PKG_VERSION="([^"]+)"', pkg, re.M)[1]
tarball = root / f"sources/vlc/vlc-{version}.tar.xz"
patch = root / "projects/ROCKNIX/devices/RK3128/patches/vlc/0001-vout-keep-the-private-data-naturally-aligned.patch"

if not tarball.exists():
    print("note: VLC source tarball not downloaded; vout alignment check skipped")
    raise SystemExit(0)

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    names = ["src/video_output/video_output.c", "src/video_output/vout_subpictures.c"]
    with tarfile.open(tarball) as tar:
        for m in tar.getmembers():
            rel = m.name.split("/", 1)[1] if "/" in m.name else ""
            if rel in names:
                m.name = rel
                tar.extract(m, tmp, filter="data")
    subprocess.run(["patch", "-p1", "-s", "-d", str(tmp)], input=patch.read_text(), text=True, check=True)
    vout = (tmp / names[0]).read_text()
    spu = (tmp / names[1]).read_text()

assert not re.search(r"\(vout_thread_sys_t\s*\*\)\s*&vout\[1\]", vout), "vout private data must not follow at &vout[1]"
assert not re.search(r"\(spu_private_t\s*\*\)\s*&spu\[1\]", spu), "spu private data must not follow at &spu[1]"
assert re.search(r"struct vout_thread_alloc \{\s*vout_thread_t\s+vout;\s*vout_thread_sys_t\s+sys;\s*\};", vout)
assert "sizeof(struct vout_thread_alloc)" in vout and "&((struct vout_thread_alloc *)vout)->sys" in vout
assert re.search(r"struct spu_alloc \{\s*spu_t\s+spu;\s*spu_private_t\s+sys;\s*\};", spu)
assert "sizeof(struct spu_alloc)" in spu and "&((struct spu_alloc *)spu)->sys" in spu
print("vlc vout alignment: ok")
