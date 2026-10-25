#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Art Book Next fits game previews inside the video panel on the A12.

The theme sizes the game video with <minSize> (cover the panel, crop the
rest), which cut off vertical and 4:3 arcade previews (owner, 2026-10-12).
On RK3128 the theme package turns every video box into <maxSize> (fit,
keep aspect) and leaves images alone. The sed command is taken from
package.mk and run on the pinned theme's XML files.
"""
import pathlib
import re
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = (root / "projects/ROCKNIX/packages/ui/themes/es-theme-art-book-next/package.mk").read_text()
version = re.search(r'^PKG_VERSION="([0-9a-f]+)"', pkg, re.M)[1]
tarball = next((root / "sources/es-theme-art-book-next").glob(f"*{version}*.tar.gz"), None)
block = re.search(r'if \[ "\$\{DEVICE\}" = "RK3128" \]; then\n(.*?)\n  fi', pkg, re.S)
assert block, "RK3128 video-fit block missing in package.mk"
expr = re.search(r"sed -i '([^']+)'", block[1])[1]

if tarball is None:
    print("note: theme source tarball not downloaded; video fit check skipped")
    raise SystemExit(0)

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    with tarfile.open(tarball) as tar:
        for m in tar.getmembers():
            name = m.name.split("/", 1)[-1]
            if re.fullmatch(r"(theme|aspect-ratio-[0-9-]+)\.xml", name):
                m.name = name
                tar.extract(m, tmp, filter="data")
    files = sorted(tmp.glob("*.xml"))
    before = {f.name: f.read_text() for f in files}
    subprocess.run(["sed", "-i", expr] + [str(f) for f in files], check=True)
    boxes = 0
    for f in files:
        text = f.read_text()
        for video in re.findall(r"<video[ >].*?</video>", text, re.S):
            assert "minSize" not in video, f"{f.name}: video still crops"
            boxes += video.count("<maxSize>")
        # Everything outside video elements is unchanged.
        strip = lambda t: re.sub(r"<video[ >].*?</video>", "", t, flags=re.S)
        assert strip(text) == strip(before[f.name]), f"{f.name}: non-video content changed"
    assert boxes >= 17, boxes
print(f"theme video fit: ok ({boxes} video boxes)")
