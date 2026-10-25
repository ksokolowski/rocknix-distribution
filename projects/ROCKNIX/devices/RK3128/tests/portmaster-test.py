#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 image ships PortMaster (sync9).

PortMaster installed over SSH ran on the A12 (TEST_LOG, PortMaster
2026.10.03: ARMv7 helpers, KMS/GLES2 GUI, catalogue). The image now builds
ROCKNIX's portmaster package for RK3128. That package also unpacks
ROCKNIX's compat.tar.gz into /usr/lib/compat; those 50 libraries are
aarch64 builds (21 MB), so a 32-bit ARM image leaves them out.
If a build is present, the image must have the start script and no compat
libraries. GStreamer is left out on 32-bit ARM (see below).
"""
import pathlib
import re
import subprocess

root = pathlib.Path(__file__).resolve().parents[5]
emus = (root / "projects/ROCKNIX/packages/virtual/emulators/package.mk").read_text()
pm = root / "projects/ROCKNIX/packages/apps/portmaster/package.mk"

a12 = re.search(r"^  RK3128\)\n(.*?)\n    ;;", emus, re.M | re.S)[1]
pkg_emus = re.search(r'PKG_EMUS="([^"]*)"', a12)[1].split()
assert "portmaster" in pkg_emus, f"RK3128 PKG_EMUS lacks portmaster: {pkg_emus}"


def compat_steps(arch):
    """The makeinstall_target lines that would run, with commands stubbed."""
    script = f'''
ARCH={arch}; INSTALL=/i; PKG_DIR=/p; PKG_BUILD=/b; PKG_URL=u; COMPAT_URL=c
mkdir() {{ :; }}; cp() {{ :; }}; rm() {{ :; }}
curl() {{ echo "curl $*"; }}; tar() {{ echo "tar $*"; }}
get_pkg_directory() {{ echo /pkgs/$1; }}
. "{pm}" >/dev/null
makeinstall_target
'''
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout


def depends(arch):
    script = f'ARCH={arch}; get_pkg_directory() {{ :; }}; . "{pm}" >/dev/null; echo "$PKG_DEPENDS_TARGET"'
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout.split()


# gst-plugins-base does not build for 32-bit ARM (audio-resampler's Thumb-2
# inline assembly in ARM mode, sync9 build); PortMaster ran on the A12
# without GStreamer, so 32-bit ARM leaves it out.
assert "gst-plugins-base" not in depends("arm"), depends("arm")
assert "gst-plugins-base" in depends("aarch64") and "oga_controls" in depends("arm")

arm, aarch64 = compat_steps("arm"), compat_steps("aarch64")
assert "PortMaster.zip" in arm, arm                  # the release zip on every arch
assert "compat" not in arm, f"32-bit ARM unpacks the aarch64 compat libraries:\n{arm}"
assert "compat.tar.gz" in aarch64, aarch64           # aarch64 unchanged

# sync9 on the A12 (2026-10-25): the GUI stayed black. Its unpacking filled
# the RAM-backed /tmp (90.7 of 112 MB) and the 256 MB device thrashed; and
# the zip's generic helper names (gptokeyb, gptokeyb2, xdelta3, ...) are
# aarch64 builds next to .armhf ones. The owner's hand-made launcher that
# worked did both of these; start_portmaster.sh now does them for all.
start = (root / "projects/ROCKNIX/packages/apps/portmaster/scripts/start_portmaster.sh").read_text()
tmpdir = start.find("export TMPDIR=/storage/")
assert tmpdir != -1 and tmpdir < start.find("./PortMaster.sh"), "TMPDIR must point at /storage before PortMaster runs"
helpers = re.search(r'case "\$\(uname -m\)" in\n\s*armv7\*\|armv8l\)(.*?);;', start, re.S)
assert helpers and ".armhf" in helpers[1] and "gptokeyb" in helpers[1], "32-bit ARM must use the .armhf helpers"
assert helpers.start() < start.find("cp /storage/roms/ports/PortMaster/gptokeyb gptokeyb"), \
    "the armhf copies must be in place before gptokeyb is copied to the config"

image = root / "build.ROCKNIX-RK3128.arm/image/system/usr"
if image.is_dir():
    assert (image / "bin/start_portmaster.sh").is_file(), "built image lacks start_portmaster.sh"
    assert not (image / "lib/compat").exists(), "built image has the aarch64 compat libraries"
    print("portmaster: ok (built image checked)")
else:
    print("portmaster: ok")
