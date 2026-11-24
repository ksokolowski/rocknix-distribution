#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""VLC follows FFmpeg's ABI on the A12 (sync 2026-10-17).

The sync moved FFmpeg 7.1.1 -> 9.0 (libavcodec.so.61 -> .so.63). VLC's
package was unchanged, so the build kept the old VLC plugins: avcodec,
avformat and swscale linked sonames the image no longer had, and ES
previews decoded nothing. The A12 VLC now names FFmpeg's package in
PKG_NEED_UNPACK, so a FFmpeg change rebuilds it. If a build is present,
no file in the image may link an FFmpeg soname the image does not ship.
"""
import os
import pathlib
import re
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
pkg = root / "projects/ROCKNIX/packages/multimedia/vlc/package.mk"

out = subprocess.run(["bash", "-c", f'''
get_pkg_directory() {{ echo "/pkgs/$1"; }}
target_has_feature() {{ return 1; }}
DEVICE=RK3128; ARCH=arm; DISPLAYSERVER=no; OPENGLES=; . "{pkg}" >/dev/null 2>&1
echo "$PKG_NEED_UNPACK"'''], check=True, capture_output=True, text=True).stdout.split()
assert "/pkgs/ffmpeg" in out, f"A12 VLC does not rebuild on FFmpeg changes: PKG_NEED_UNPACK={out}"

image = root / "build.ROCKNIX-RK3128.arm/image/system"
if not (image / "usr/lib").is_dir():
    print("vlc ffmpeg rebuild: ok (no built image; soname scan skipped)")
    raise SystemExit(0)
shipped = {p.name for p in (image / "usr/lib").iterdir()}
stale = []
for dirpath, _, files in os.walk(image):
    for name in files:
        f = pathlib.Path(dirpath) / name
        if f.is_symlink() or not (".so" in name or os.access(f, os.X_OK)):
            continue
        try:
            dyn = subprocess.run(["readelf", "-d", str(f)], capture_output=True, text=True).stdout
        except OSError:
            continue
        for lib in re.findall(r"\[(lib(?:av|sw|postproc)[a-z]*\.so\.\d+)\]", dyn):
            if lib not in shipped:
                stale.append(f"{f.relative_to(image)} -> {lib}")
assert not stale, "files linked to FFmpeg sonames the image lacks:\n" + "\n".join(stale)
print("vlc ffmpeg rebuild: ok")
