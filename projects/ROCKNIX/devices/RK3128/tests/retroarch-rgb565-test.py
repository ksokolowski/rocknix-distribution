#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""RetroArch KMS can scan out RGB565 when RETROARCH_KMS_RGB565=1 (A12 experiment).

The A12 panel is RGB666 and its 16-bit DDR3 bus is the bottleneck; an
RGB565 framebuffer halves scanout and GPU writeback traffic and the CMA
taken by the swap chain. Default (unset) keeps XRGB8888 unchanged. The
patch must apply after the shared RetroArch patches to the pinned source.
"""
import pathlib
import re
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = root / "projects/ROCKNIX/packages/emulators/libretro/retroarch"
patch = (root / "projects/ROCKNIX/devices/RK3128/patches/retroarch/0001-drm-optional-rgb565-scanout.patch").read_text()
version = re.search(r'^PKG_VERSION="([0-9a-f]+)"', (pkg / "package.mk").read_text(), re.M)[1]
member_rel = "gfx/drivers_context/drm_ctx.c"

added = "\n".join(l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))
assert 'getenv("RETROARCH_KMS_RGB565")' in added
assert "GBM_FORMAT_RGB565" in added and "r != 5 || g != 6 || b != 5" in added
assert re.search(r"drmModeAddFB\(g_drm_fd, width, height,\s*\n?\s*drm_use_rgb565\(\) \? 16 : 24, drm_use_rgb565\(\) \? 16 : 32", added)
assert added.count("drm_gbm_format()") >= 2  # both gbm_surface_create calls

tarball = root / f"sources/retroarch/retroarch-{version}.tar.gz"
if not tarball.exists():
    print("note: RetroArch source tarball not downloaded; dry-run skipped")
    print("retroarch rgb565 option: ok")
    raise SystemExit(0)

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    with tarfile.open(tarball) as tar:
        member = next(n for n in tar.getnames() if n.endswith(f"-{version}/{member_rel}"))
        tar.extract(member, tmp, filter="data")
    src = tmp / member.split("/", 1)[0]
    for shared in sorted((pkg / "patches").glob("*.patch")):
        if member_rel in shared.read_text(errors="replace"):
            subprocess.run(["patch", "-p1", "-s", "-d", str(src)], input=shared.read_text(),
                           text=True, check=True)
    subprocess.run(["patch", "-p1", "-s", "-d", str(src)], input=patch, text=True, check=True)
    code = (src / member_rel).read_text()
    assert "GBM_FORMAT_XRGB8888" in code, "default must stay XRGB8888"
print("retroarch rgb565 option: ok")
