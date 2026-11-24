#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""B12 step 4: opt-in KMS logo from the initramfs (a12_kms_splash).

load_splash runs after mount_sysroot, so the system image's a12-splash can
draw the logo through that image's own loader. Only with the kernel
argument a12_kms_splash; rocknix-splash (fbdev) stays the default and the
fallback when a12-splash is missing or fails.
"""
import os
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
init = (root / "projects/ROCKNIX/packages/sysutils/busybox/scripts/init").read_text()
funcs = "".join(re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", init, re.M | re.S)[0]
                for name in ("a12_kms_logo", "load_splash"))
assert re.search(r"^    a12_kms_splash\)\n      A12_KMS_SPLASH=yes\n      ;;$", init, re.M)
main = (root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/sources/splash/splash-main.c").read_text()
assert 'strcmp(mode, "--logo") == 0 ? 1 : 0' in main, "--logo must fail visibly so init falls back"


def boot(flag, splash_rc=0, install=True, tool_rc=None):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        log = tmp / "log"
        sysroot = tmp / "sysroot"
        (sysroot / "usr/lib").mkdir(parents=True)
        (sysroot / "usr/bin").mkdir()
        loader = sysroot / "usr/lib/ld-linux-armhf.so.3"
        loader.write_text(f'#!/bin/sh\necho "loader $* logo=$A12_SPLASH_LOGO" >> {log}\nexit {splash_rc}\n')
        loader.chmod(0o755)
        if install:
            (sysroot / "usr/bin/a12-splash").write_text("")
            (sysroot / "usr/bin/a12-splash").chmod(0o755)
        tool = tmp / "a12-update-splash"
        if tool_rc is not None:
            tool.write_text(f'#!/bin/sh\necho "update-splash [$1]" >> {log}\nexit {tool_rc}\n')
            tool.chmod(0o755)
        rs = tmp / "rocknix-splash"
        rs.write_text(f"#!/bin/sh\necho rocknix-splash >> {log}\n")
        rs.chmod(0o755)
        body = (funcs.replace("/usr/bin/a12-update-splash", str(tool)).replace("/sysroot", str(sysroot)).replace("/usr/bin/rocknix-splash", str(rs))
                .replace("/dev/console", "/dev/null").replace("$(cat /sysroot/etc/issue)", "")
                .replace(f"$(cat {sysroot}/etc/issue)", ""))
        script = f"A12_KMS_SPLASH={flag}\n{body}\nload_splash\n"
        subprocess.run(["sh", "-c", script], check=True, env=dict(os.environ, HOME=str(tmp)))
        return log.read_text().splitlines()


assert boot("") == ["rocknix-splash"], "default: rocknix-splash only"
out = boot("yes")
assert len(out) == 1 and out[0].startswith("loader --library-path ") and out[0].endswith(
    "/usr/bin/a12-splash --logo logo=" + out[0].split("logo=")[1]), out
assert out[0].split("logo=")[1].endswith("/sysroot/usr/share/a12-splash/logo.bmp")
failed = boot("yes", splash_rc=1)
assert len(failed) == 2 and failed[0].startswith("loader ") and failed[1] == "rocknix-splash", failed
assert boot("yes", install=False) == ["rocknix-splash"], "no a12-splash: rocknix-splash"
# No-fbdev builds (test 61): the initramfs's own a12-update-splash draws the
# logo, independent of the system image; exit 2 (fbdev present) falls back.
assert boot("yes", tool_rc=0) == ["update-splash []"]
fb = boot("yes", tool_rc=2)
assert fb[0] == "update-splash []" and fb[1].startswith("loader ") and len(fb) == 2, fb
assert boot("", tool_rc=0) == ["rocknix-splash"], "default: the tool is not used"
# Earlier logo (test 61): the display driver is up before /init runs, so the
# A12's own tool draws the logo as the very first boot step, before module
# loading, disk checks and mounts; load_splash draws it again later.
seq = init[init.index("# main boot sequence"):]
seq = seq[seq.index("for BOOT_STEP in \\\n") + len("for BOOT_STEP in \\\n"):]
assert seq.split()[0] == "a12_early_logo", seq.split()[:3]
early = re.search(r"^a12_early_logo\(\) \{\n.*?^\}\n", init, re.M | re.S)[0]


def early_run(flag, tool_exists):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        log = tmp / "log"
        tool = tmp / "a12-update-splash"
        if tool_exists:
            tool.write_text(f'#!/bin/sh\necho "early [$1]" >> {log}\n')
            tool.chmod(0o755)
        script = f"A12_KMS_SPLASH={flag}\n" + early.replace("/usr/bin/a12-update-splash", str(tool)) + "a12_early_logo\n"
        subprocess.run(["sh", "-c", script], check=True)
        return log.read_text().splitlines() if log.exists() else []


assert early_run("yes", True) == ["early []"]
assert early_run("", True) == [] and early_run("yes", False) == []
print("initramfs kms logo: ok")
