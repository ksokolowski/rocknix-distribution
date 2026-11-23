#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12's Virtual Boy speed patches stay until upstream has them.

beetle_vb ran at 1.1-1.5x headless on the A12 before patches 0001-0005;
with them the owner plays Virtual Boy games at full speed (2026-10-25:
"fully playable now", a rare system the A12/A13 can run thanks to them).
They are sent upstream as libretro/beetle-vb-libretro #97-#100 (tracker
VB01-VB05), not merged yet. An upstream sync that bumps the core or drops
the patch directory must not lose them silently: drop a patch here only
when the pinned PKG_VERSION contains the merged upstream change.
"""
import pathlib
import re

root = pathlib.Path(__file__).resolve().parents[5]
patches = root / "projects/ROCKNIX/devices/RK3128/patches/beetle-vb-lr"
emus = (root / "projects/ROCKNIX/packages/virtual/emulators/package.mk").read_text()

expected = {
    "0001": "vip-stage-anaglyph-output-and-write-it-row-by-row",
    "0002": "skip-idle-xpstts-polling-loops-in-whole-loop-periods",
    "0003": "v810-load-and-store-plain-memory-directly",
    "0004": "idle-skip-take-the-register-snapshot-only-for-repeating-loops",
    "0005": "vip-skip-fully-transparent-background-character-rows",
}
have = {p.name[:4]: p.name[5:-6] for p in patches.glob("*.patch")}
for number, name in expected.items():
    assert have.get(number) == name, f"Virtual Boy patch {number}-{name} is missing (upstream not merged yet)"
    text = (patches / f"{number}-{name}.patch").read_text()
    assert text.startswith("From ") or "\n--- a/" in text, f"{number} is not a patch"

a12 = re.search(r"^  RK3128\)\n(.*?)\n    ;;", emus, re.M | re.S)[1]
assert "beetle-vb-lr" in re.search(r'LIBRETRO_CORES="([^"]*)"', a12)[1].split(), "the A12 ships beetle_vb"
print("vb patches kept: ok")
