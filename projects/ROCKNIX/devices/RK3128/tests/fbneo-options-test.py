#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise CPS1 option migration without sourcing the device's /etc/profile."""
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
source = (root / "projects/ROCKNIX/packages/rocknix/sources/scripts/setsettings.sh").read_text()
function = source.split("function set_fbneoopts() {", 1)[1].split("\n}\n", 1)[0]
function = "function set_fbneoopts() {" + function + "\n}\n"

with tempfile.TemporaryDirectory(prefix="a12-fbneo-options-") as temporary:
    config = pathlib.Path(temporary)
    options = config / "config/FinalBurn Neo"
    options.mkdir(parents=True)
    core = options / "FinalBurn Neo.opt"
    original = 'fbneo-cyclone = "disabled"\nfbneo-samplerate = "48000"\nfbneo-dipswitch-ffight-Lives = "3"\n'
    core.write_text(original)

    def run(device="RK3128", platform="cps1", core_name="fbneo", setting="", folder="cps1"):
        script = function + '\nlog() { printf "%s\\n" "$*"; }\ngame_setting() { printf "%s" "$REQUESTED"; }\nset_fbneoopts\n'
        result = subprocess.run(
            ["bash", "-eu", "-c", script],
            env={"PATH": "/usr/bin:/bin", "RETROARCH_PATH": str(config),
                 "HW_DEVICE": device, "PLATFORM": platform, "CORE": core_name,
                 "ROM": "ffight.zip", "ROM_FOLDER": folder, "REQUESTED": setting},
            capture_output=True, text=True,
        )
        if result.returncode:
            raise AssertionError(result.stderr or result.stdout)
        return result.stdout

    folder = options / "cps1.opt"
    run(device="RK3326")
    run(platform="neogeo")
    run(core_name="mame2003_plus")
    assert not folder.exists(), "Other targets, systems and cores must be unchanged"

    assert "Cyclone: enabled" in run()
    assert set(folder.read_text().splitlines()) == set(original.replace('"disabled"', '"enabled"').splitlines())
    assert core.read_text() == original, "Core-wide settings must be preserved"

    folder.write_text(folder.read_text().replace('"enabled"', '"disabled"'))
    assert "Cyclone: disabled" in run(), "Saved menu choices must survive relaunch"
    assert "Cyclone: enabled" in run(setting="enabled")
    assert "Cyclone: disabled" in run(setting="disabled")
    assert folder.read_text().count("fbneo-cyclone") == 1

    game = options / "ffight.opt"
    game.write_text('fbneo-cyclone = "disabled"\n')
    assert "Cyclone: disabled" in run(setting="enabled"), "Game options have precedence"
    assert game.read_text() == 'fbneo-cyclone = "disabled"\n'

    assert "Cyclone: disabled" in run(folder="CPS1 collection"), "Game override still applies"
    assert 'fbneo-cyclone = "enabled"' in (options / "CPS1 collection.opt").read_text()

    other_config = config / "fresh"
    other_config.mkdir()
    config = other_config
    run()
    assert (config / "config/FinalBurn Neo/cps1.opt").read_text() == 'fbneo-cyclone = "enabled"\n'

print("A12 CPS1 Cyclone migration and option precedence: OK")
