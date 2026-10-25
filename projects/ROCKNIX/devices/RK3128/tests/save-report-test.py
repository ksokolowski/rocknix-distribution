#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-save-report keeps the previous boot's reports and link history.

BACKLOG open issue: a network loss on the first boot after an update was not
captured; the in-RAM journal had rotated and the next boot overwrote the
45 s boot report. The previous boot now moves to prev/, and the hardware
report prints per-interface carrier counters, which survive rotation.
"""
import os
import pathlib
import subprocess
import tempfile

device = pathlib.Path(__file__).resolve().parents[1]
sources = device / "packages/a12-controls/sources"
script = sources / "a12-save-report"

with tempfile.TemporaryDirectory(prefix="a12-report-") as temporary:
    root = pathlib.Path(temporary)
    output, bin_dir, pstore = root / "diag", root / "bin", root / "pstore"
    bin_dir.mkdir()
    pstore.mkdir()
    for name, body in {"a12-hardware-report": 'echo "hw $A12_BOOT_ID"', "systemctl": "exit 0",
                       "dmesg": "exit 0", "journalctl": 'echo "journal $A12_BOOT_ID"',
                       "sync": "exit 0"}.items():
        (bin_dir / name).write_text("#!/bin/sh\n" + body + "\n")
        (bin_dir / name).chmod(0o755)
    base = dict(os.environ, PATH=f"{bin_dir}:/usr/bin:/bin", A12_PSTORE_DIR=str(pstore),
                A12_DIAGNOSTICS_DIR=str(output), A12_HARDWARE_REPORT=str(bin_dir / "a12-hardware-report"))

    def run(phase, boot):
        subprocess.run(["sh", str(script), phase], env=dict(base, A12_BOOT_ID=boot), check=True)

    def text(path):
        return (output / path).read_text().strip()

    run("boot", "one")
    run("shutdown", "one")
    assert not (output / "prev").exists() or not any((output / "prev").iterdir())
    run("boot", "two")
    assert text("prev/boot-id") == "one"
    assert text("prev/boot-hardware.txt").startswith("hw one")
    assert text("prev/shutdown-journal.txt") == "journal one"
    assert text("boot-id") == "two" and text("boot-hardware.txt").startswith("hw two")
    assert not (output / "shutdown-journal.txt").exists(), "a stale shutdown report must not stay current"
    run("boot", "two")   # rerun in the same boot: no rotation
    assert text("prev/boot-id") == "one"
    # Boot two never shut down cleanly (power cut): prev/ holds only its boot report.
    run("boot", "three")
    assert text("prev/boot-id") == "two"
    assert not (output / "prev/shutdown-journal.txt").exists()

report = (sources / "a12-hardware-report").read_text()
for counter in ("carrier_changes", "carrier_up_count", "carrier_down_count"):
    assert counter in report, counter
print("save report: ok")
