#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""B9: the A12 recompresses idle zram pages with zstd, never during a game.

Test 41: zstd recompression of idle pages shrinks zram by 2.1-2.7 MiB for
about 3 s of one core and needed an idle-time trigger. Upstream ROCKNIX
(sync 2026-10-11) added recompress_idle(), a disabled 10-minute timer and
games.slice for running games. The A12 keeps lzo-rle as the primary
algorithm, names zstd in ZRAM_RECOMP_ALGO, enables the timer and skips a
run while games.slice is populated.
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
device = root / "projects/ROCKNIX/devices/RK3128"
manager = (root / "projects/ROCKNIX/packages/rocknix/sources/scripts/rocknix-memory-manager").read_text()
block = manager[manager.index("# Determine Algorithms"):manager.index("# --- 6. PERFORM ACTION ---")]


def algorithms(zram_algo, recomp):
    with tempfile.TemporaryDirectory() as tmp:
        body = block.replace("/sys/block/zram0/comp_algorithm", f"{tmp}/comp_algorithm")
        pathlib.Path(tmp, "comp_algorithm").write_text("lzo [lzo-rle] lz4 zstd\n")
        script = f'ZRAM_ALGO="{zram_algo}"\nZRAM_RECOMP_ALGO="{recomp}"\n{body}\necho "$PRIMARY_ALGO $SECONDARY_ALGO"\n'
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout.split()


assert algorithms("lzo-rle", "zstd") == ["lzo-rle", "zstd"], "A12: lzo-rle primary, zstd secondary"
assert algorithms("lzo-rle", "") == ["lzo-rle"], "unset: no recompression (other devices)"
assert algorithms("lzo-rle", "@ZRAM_RECOMP_ALGO@") == ["lzo-rle"], "unsubstituted template: off"
assert algorithms("zstd", "") == ["lz4", "zstd"], "upstream zstd hybrid unchanged"
assert algorithms("lzo-rle", "lzo-rle") == ["lzo-rle"], "same algorithm twice: off"

# Wiring: template, substitution, A12 option, timer link and game guard.
assert 'ZRAM_RECOMP_ALGO="@ZRAM_RECOMP_ALGO@"' in (root / "projects/ROCKNIX/packages/sysutils/util-linux/config/swap.conf").read_text()
assert "s,@ZRAM_RECOMP_ALGO@,${ZRAM_RECOMP_ALGO},g" in (root / "projects/ROCKNIX/packages/sysutils/util-linux/package.mk").read_text()
assert re.search(r'^ZRAM_RECOMP_ALGO="zstd"$', (device / "options").read_text(), re.M)
assert re.search(r'^ZRAM_COMPRESSION_ALGO="lzo-rle"$', (device / "options").read_text(), re.M)
mk = (device / "packages/a12-controls/package.mk").read_text()
assert 'ln -sf ../rocknix-memory-recompress.timer "${INSTALL}/usr/lib/systemd/system/timers.target.wants/"' in mk
assert (root / "projects/ROCKNIX/packages/rocknix/system.d/rocknix-memory-recompress.timer").exists()
assert '--recompress) ACTION="recompress"' in manager

dropin = (device / "packages/quirks/system.d/rocknix-memory-recompress.service.d/10-a12-no-game.conf").read_text()
condition = re.search(r"^ExecCondition=/bin/sh -c '(.*)'$", dropin, re.M)[1]
with tempfile.TemporaryDirectory() as tmp:
    events = pathlib.Path(tmp, "games.slice/cgroup.events")
    check = condition.replace("/sys/fs/cgroup", tmp)

    def runs():
        return subprocess.run(["sh", "-c", check]).returncode == 0

    assert runs(), "no games.slice yet (no game since boot): run"
    events.parent.mkdir()
    events.write_text("populated 1\nfrozen 0\n")
    assert not runs(), "a game is running: skip"
    events.write_text("populated 0\nfrozen 0\n")
    assert runs(), "game ended: run"
print("zram recompress: ok")
