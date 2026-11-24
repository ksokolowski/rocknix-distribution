#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The VOP has no IOMMU here, so every 1024x600 scanout buffer is CMA.

2026-10-08 (boot f8f51dd6): with 16 MiB RetroArch's KMS buffers failed
(DRM_IOCTL_MODE_CREATE_DUMB ENOMEM, 12160 failed CMA pages) and it segfaulted at
launch even after compaction; with cma=32M (boot 4c9f6d53) four launches had no
failures.
"""
import pathlib
import re

config = (pathlib.Path(__file__).resolve().parents[1] / "linux/linux.arm.conf").read_text()
size = re.search(r"^CONFIG_CMA_SIZE_MBYTES=(\d+)$", config, re.M)
assert size, "CMA size not set"
assert int(size[1]) >= 32, f"CMA {size[1]} MiB is too small for RetroArch plus ES and fbcon"
print("cma size: ok")
