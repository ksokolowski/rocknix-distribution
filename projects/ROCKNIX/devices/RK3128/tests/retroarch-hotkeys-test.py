#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise launcher hotkeys with the real A12 joypad autoconfiguration."""
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
source = (root / "projects/ROCKNIX/packages/rocknix/sources/scripts/setsettings.sh").read_text()
function = "function configure_hotkeys() {" + source.split(
    "function configure_hotkeys() {", 1)[1].split("\n}\n", 1)[0] + "\n}\n"
joypad = root / "projects/ROCKNIX/packages/emulators/libretro/retroarch/retroarch-joypads/gamepads/stick.cfg"

with tempfile.TemporaryDirectory(prefix="a12-retroarch-hotkeys-") as temporary:
    directory = pathlib.Path(temporary)
    pads = directory / "joypads"
    pads.mkdir()
    config = directory / "retroarch.cfg"
    devices = directory / "devices"
    function = function.replace("/tmp", str(directory)).replace("/proc/bus/input/devices", str(devices))

    def run(device="RK3128", controller="stick", automatic="1"):
        devices.write_text(f'I: Bus=0019\nN: Name="{controller}"\nP: Phys=test\nS: Sysfs=test\nH: Handlers=event0 js0\n')
        (pads / (controller + ".cfg")).write_text(joypad.read_text())
        config.write_text('input_menu_toggle_btn = "42"\ninput_enable_hotkey_btn = "99"\n')
        script = function + '''
log() { :; }
get_setting() { printf '%s' "$AUTOMATIC"; }
clear_setting() { sed -i "/^$1 =/d" "$RETROARCH_CONFIG"; }
flush_settings() { :; }
configure_hotkeys
'''
        subprocess.run(["bash", "-e", "-c", script], check=True,
                       env={"PATH": "/usr/bin:/bin", "HW_DEVICE": device,
                            "RETROARCH_CONFIG": str(config), "AUTOMATIC": automatic})
        return dict(line.split(" = ", 1) for line in config.read_text().splitlines())

    settings = run()
    assert settings["input_menu_toggle_btn"] == '"8"', "Physical Back must open RGUI"
    assert settings["input_enable_hotkey_btn"] == '"8"'
    assert settings["input_exit_emulator_btn"] == '"7"', "Back+Start quit must survive"
    assert settings["input_save_state_btn"] == '"5"'
    assert settings["input_load_state_btn"] == '"4"'
    # Elsewhere the menu toggle is the profile's X button (stick.cfg, test 62).
    x_btn = next(l.split(" = ", 1)[1] for l in joypad.read_text().splitlines() if l.startswith("input_x_btn"))
    assert run(device="RK3326")["input_menu_toggle_btn"] == x_btn
    assert run(controller="external pad")["input_menu_toggle_btn"] == x_btn
    assert run(automatic="0")["input_menu_toggle_btn"] == '"42"', "Respect manual hotkeys"

print("A12 Back menu, existing chords and manual/external controller settings: OK")
