#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import os
from pathlib import Path
import subprocess
import tempfile

writer = (Path(__file__).resolve().parents[1] / "bootloader/mkimage").read_text()
writer = writer.split('\n. "${PROJECT_DIR}')[0]
with tempfile.TemporaryDirectory(prefix="a12-image-test-") as temporary:
    root = Path(temporary)
    boot = root / "3rdparty/bootloader"
    boot.mkdir(parents=True)
    payloads = {"idbloader.img": b"I" * 512, "uboot.img": b"U" * 1024,
                "trust.img": b"T" * 1024}
    for name, data in payloads.items():
        (boot / name).write_bytes(data)
    disk = root / "image"
    disk.write_bytes(b"")
    with disk.open("r+b") as image:
        image.truncate(32 * 1024 * 1024)
    environment = dict(os.environ, RELEASE_DIR=str(root), DISK=str(disk),
                       SAVE_ERROR=str(root / "error"), SYSTEM_PART_START="32768")
    script = "show_error() { exit 97; }\n" + writer + "\nmkimage_uboot_device\n"
    subprocess.run(["bash", "-c", script], env=environment, check=True)
    content = disk.read_bytes()
    for name, offset in [("idbloader.img", 32768), ("uboot.img", 8388608),
                         ("trust.img", 12582912)]:
        data = payloads[name]
        assert content[offset:offset + len(data)] == data
        assert content[offset - 512:offset] == bytes(512)
    assert content[16 * 1024 * 1024:] == bytes(16 * 1024 * 1024)
    environment["SYSTEM_PART_START"] = "16384"
    result = subprocess.run(["bash", "-c", script], env=environment)
    assert result.returncode == 97
    assert disk.read_bytes() == content
    environment["SYSTEM_PART_START"] = "32768"
    with (boot / "uboot.img").open("wb") as image:
        image.truncate(4 * 1024 * 1024 + 1)
    result = subprocess.run(["bash", "-c", script], env=environment)
    assert result.returncode == 97
    assert disk.read_bytes() == content
print("A12 bootloader offsets and overlap guards passed")
