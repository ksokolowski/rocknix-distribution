#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Lima closes its screen fd, so ES does not leak a render node per game.

Test 43 (2026-10-11): every ES game launch left one /dev/dri/renderD128
descriptor and one Lima DRM client open (SDL_Quit -> eglTerminate ->
gbm_device_destroy). lima_drm_screen_create_renderonly() dups the fd into
screen->fd, but lima_screen_destroy() and lima_screen_create()'s failure
paths never close it; v3d and vc4, created the same way, do. Upstream Mesa
main has the same code. The patch must apply to the pinned Mesa source.
"""
import pathlib
import re
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
patch = (root / "projects/ROCKNIX/devices/RK3128/patches/mesa/0001-lima-close-the-screen-fd.patch").read_text()
version = re.search(r'^PKG_VERSION="([^"]+)"', (root / "projects/ROCKNIX/packages/graphics/mesa/package.mk").read_text(), re.M)[1]

assert "src/gallium/drivers/lima/lima_screen.c" in patch
added = [l[1:].strip() for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++")]
assert added.count("close(screen->fd);") == 2, added   # destroy and err_out0
assert added.count("close(fd);") == 1, added           # allocation failure
assert "#include <unistd.h>" in added, "close() needs <unistd.h>"

tarball = next((root / "sources/mesa").glob(f"mesa-{version}.tar.*"), None)
if tarball:
    with tempfile.TemporaryDirectory() as tmp:
        # The top directory follows the archive URL (mesa-<commit>/, mesa-mesa-<release>/).
        with tarfile.open(tarball) as tar:
            member = next(m for m in tar.getnames() if m.endswith("/src/gallium/drivers/lima/lima_screen.c"))
            tar.extract(member, tmp, filter="data")
        src = pathlib.Path(tmp) / member.split("/")[0]
        subprocess.run(["patch", "-p1", "--dry-run", "-d", str(src)], input=patch, text=True,
                       check=True, capture_output=True)
        subprocess.run(["patch", "-p1", "-s", "-d", str(src)], input=patch, text=True, check=True)
        code = (src / "src/gallium/drivers/lima/lima_screen.c").read_text()
        destroy = re.search(r"^lima_screen_destroy\(.*?^\}", code, re.S | re.M)[0]
        assert "close(screen->fd);" in destroy
        assert destroy.index("close(screen->fd);") < destroy.index("ralloc_free(screen);")
else:
    print("note: Mesa source tarball not downloaded; dry-run skipped")
print("lima screen fd: ok")
