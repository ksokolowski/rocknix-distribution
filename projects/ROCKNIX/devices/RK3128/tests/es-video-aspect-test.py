#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""ES honours a preview video's sample aspect ratio (A12 ES patch 0001).

Scraped MAME previews with non-square pixels showed distorted (owner,
2026-10-12): galaxian is coded 224x768 with an 18:7 sample aspect (display
3:4) and appeared as a thin strip. The patched applySampleAspect() is taken
from the pinned ES source with the patch applied, compiled and checked; it
must shrink one side only, to the display aspect.
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
patch = root / "projects/ROCKNIX/devices/RK3128/patches/emulationstation/0001-video-honour-sample-aspect-ratio.patch"
src = "es-core/src/components/VideoVlcComponent.cpp"

if not tarball.exists():
    print("note: ES source tarball not downloaded; video aspect patch check skipped")
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
    assert "applySampleAspect(mVideoWidth, mVideoHeight, tracks[track]->video->i_sar_num, tracks[track]->video->i_sar_den);" in code
    func = re.search(r"^static void applySampleAspect\(.*?^\}\n", code, re.M | re.S)[0]
    (tmp / "t.cpp").write_text("#include <algorithm>\n#include <cassert>\n#include <cstdio>\n" + func + r'''
static void check(unsigned w, unsigned h, unsigned n, unsigned d, unsigned ew, unsigned eh)
{
	applySampleAspect(w, h, n, d);
	if (w != ew || h != eh) { std::printf("got %ux%u want %ux%u\n", w, h, ew, eh); assert(false); }
}
int main()
{
	check(224, 768, 18, 7, 224, 298);  // galaxian: display 3:4
	check(224, 288, 27, 28, 216, 288); // galaga
	check(224, 256, 6, 7, 192, 256);   // dkong: display 3:4
	check(384, 224, 1, 1, 384, 224);   // square pixels unchanged
	check(384, 224, 0, 0, 384, 224);   // unknown aspect unchanged
	std::puts("es video aspect: ok");
}
''')
    subprocess.run(["g++", "-Wall", "-Werror", "-o", str(tmp / "t"), str(tmp / "t.cpp")], check=True)
    subprocess.run([str(tmp / "t")], check=True)
