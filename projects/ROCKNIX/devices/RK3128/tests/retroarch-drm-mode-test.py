#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""RetroArch reads /var/run/drmMode only once the encoder is known (2026-11-11).

The shared patch 0004-drm-resolution sets the mode chosen in ES when
/var/run/drmMode exists. Written for the old drm_common.c, it applied with
fuzz to the 2026-11 RetroArch inside drm_get_resources(), before any
connector exists, so it dereferenced a NULL g_drm_connector: on sync25 every
RetroArch launch on the A12 crashed (SIGSEGV in gfx_ctx_drm_init, exit 139;
ES writes drmMode at boot). The block belongs at the end of
drm_get_encoder(). Runs when the RetroArch source tarball is in sources/.
"""
import pathlib
import re
import subprocess
import tarfile
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
pkg = root / "projects/ROCKNIX/packages/emulators/libretro/retroarch"
version = re.search(r'^PKG_VERSION="([0-9a-f]+)"', (pkg / "package.mk").read_text(), re.M)[1]
member_rel = "gfx/common/drm_common.c"
patch = pkg / "patches/0004-drm-resolution.patch"
assert "/var/run/drmMode" in patch.read_text()

tarball = root / f"sources/retroarch/retroarch-{version}.tar.gz"
if not tarball.exists():
    print("retroarch drm mode: ok (SKIP apply: RetroArch source not downloaded)")
    raise SystemExit(0)

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    with tarfile.open(tarball) as tar:
        member = next(n for n in tar.getnames() if n.endswith(f"-{version}/{member_rel}"))
        tar.extract(member, tmp, filter="data")
    src = tmp / member.split("/", 1)[0]
    for p in sorted((pkg / "patches").glob("*.patch")):
        if member_rel in p.read_text(errors="replace"):
            r = subprocess.run(["patch", "-p1", "-F0", "-d", str(src)], input=p.read_text(),
                               text=True, capture_output=True)
            assert r.returncode == 0, f"{p.name} needs fuzz or fails:\n{r.stdout}{r.stderr}"
    code = (src / member_rel).read_text()
    at = code.index("/var/run/drmMode")
    func = re.findall(r"^\w[^\n;]*\b(\w+)\([^)]*\)\n\{", code[:at], re.M)[-1]
    assert func == "drm_get_encoder", f"drmMode block is in {func}()"
    block = code[at:code.index("\n}\n", at)]
    assert "g_drm_encoder_crtc" in block, "the CRTC chosen for the encoder"
print("retroarch drm mode: ok")
