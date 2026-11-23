#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""The A12 image defaults to UTC (owner, 2026-10-24; Europe/Warsaw before).

ROCKNIX defaults to America/New_York in system.cfg, and tz-data.service links
UTC until ES has saved /storage/.cache/timezone on its first exit. The A12
sets both: system.timezone in the image's system.cfg (RK3128 only) and the
tz-data fallback via a drop-in; a saved /storage/.cache/timezone still wins
(EnvironmentFile= overrides Environment=). ES's time zone menu lists what
`timeinfo timezones` prints, from zone1970.tab, which has no UTC: without it
ES selects nothing and saves the first entry, so timeinfo lists UTC first.
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
mk = (root / "projects/ROCKNIX/packages/rocknix/package.mk").read_text()
cfg = (root / "projects/ROCKNIX/packages/rocknix/config/system/configs/system.cfg").read_text()
assert "system.timezone=America/New_York" in cfg  # shared default unchanged

block = re.search(r'if \[ "\$\{DEVICE\}" = "RK3128" \]; then\n(.*?)\n  fi\n', mk, re.S)[1]
seds = [l.strip() for l in block.splitlines() if "system.timezone" in l]
assert len(seds) == 1, block
with tempfile.TemporaryDirectory() as tmp:
    conf = pathlib.Path(tmp) / "usr/config/system/configs/system.cfg"
    conf.parent.mkdir(parents=True)
    conf.write_text(cfg)
    subprocess.run(["bash", "-c", seds[0]], env={"INSTALL": tmp, "PATH": "/usr/bin:/bin"}, check=True)
    out = conf.read_text()
    assert "system.timezone=UTC\n" in out and "America/New_York" not in out

dropin = root / "projects/ROCKNIX/devices/RK3128/packages/quirks/system.d/tz-data.service.d/10-a12-timezone.conf"
lines = [l for l in dropin.read_text().splitlines() if l and not l.startswith("#")]
assert lines == ["[Service]", "Environment=TIMEZONE=UTC"], lines
assert (root / "projects/ROCKNIX/devices/RK3128/../../../../packages/sysutils/tz/system.d/tz-data.service").resolve().read_text().count("EnvironmentFile=-/storage/.cache/timezone") == 1
timeinfo = root / "projects/ROCKNIX/packages/rocknix/sources/scripts/timeinfo"
with tempfile.TemporaryDirectory() as tmp:
    tab = pathlib.Path(tmp) / "zone1970.tab"
    tab.write_text("# comment\nDE\t+5230+01322\tEurope/Berlin\nPL\t+5215+02100\tEurope/Warsaw\n")
    script = timeinfo.read_text().replace("/usr/share/zoneinfo/zone1970.tab", str(tab))
    out = subprocess.run(["bash", "-c", script, "timeinfo", "timezones"], capture_output=True, text=True, check=True).stdout
    assert out.split() == ["UTC,", "Europe/Berlin,", "Europe/Warsaw,"], out
print("timezone default: ok")
