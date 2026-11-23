#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""A12 game defaults: CPU performance governor unless chosen, 60 Hz refresh.

The ES menu runs schedutil (owner 2026-10-25). ROCKNIX's 008-perfmode
picks ondemand for the menu when the kernel has it, else performance; the
A12 kernel has no ondemand, so the menu sat at 1200 MHz. The image now sets
system.cpugovernor=schedutil; 008-perfmode keeps a set value. Measured at
the idle menu without forking samplers: 216 MHz half of the time.
Games: get_setting checks system.cpugovernor (ES's "default scaling
governor", menu and games) before global.cpugovernor, so the quirk's old
global default never applied; it only seemed to while the menu ran
performance (found 2026-10-25 with Olduvai under schedutil). runemu now
takes DEVICE_GAME_CPU_GOVERNOR when no system or game governor is set,
like DEVICE_GAME_GPU_PERFORMANCE; a user's per-system or per-game choice
still wins.

Owner decision 2026-10-11: games and emulators run with CPU and GPU at full
speed. RetroArch syncs to the panel refresh: by default the 60-hblank mode,
54 MHz / (1395 x 645) = 60.015 Hz (test 49); with panel_a12.refresh_60hz=0
the native mode, delivered as 594 MHz / 8 = 74.25 MHz / (1354 x 645).
Quirk 026-refresh_rate moves RetroArch between those two rates to match the
active panel mode and leaves any other rate alone.
"""
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
rocknix_mk = (root / "projects/ROCKNIX/packages/rocknix/package.mk").read_text()
a12_block = re.search(r'if \[ "\$\{DEVICE\}" = "RK3128" \]; then\n(.*?)\n  fi\n', rocknix_mk, re.S)[1]
assert 'echo "system.cpugovernor=schedutil" >>' in a12_block, "the A12 menu governor is schedutil"
perfmode = (root / "projects/ROCKNIX/packages/rocknix/autostart/008-perfmode").read_text()
assert 'if [ -z "$(get_setting system.cpugovernor)" ]' in perfmode, "008-perfmode must keep a set menu governor"
refresh_quirk = root / "projects/ROCKNIX/packages/hardware/quirks/platforms/RK3128/026-refresh_rate"
quirk = root / "projects/ROCKNIX/packages/hardware/quirks/platforms/RK3128/015-game_settings"
retroarch = root / "projects/ROCKNIX/packages/emulators/libretro/retroarch/sources/RK3128/retroarch.cfg"




assert not quirk.exists(), "the game governor comes from DEVICE_GAME_CPU_GOVERNOR, not a quirk"
device_config = (root / "projects/ROCKNIX/packages/hardware/quirks/platforms/RK3128/001-device_config").read_text()
assert 'DEVICE_GAME_CPU_GOVERNOR="performance"' in device_config

# What runemu actually picks: its governor lines run with the real get_setting.
runemu = (root / "projects/ROCKNIX/packages/rocknix/sources/scripts/runemu.sh").read_text()
block = re.search(r"^### Set the governor mode for emulation\n(.*?)^\$\{CPU_GOVERNOR\}\n", runemu, re.M | re.S)[1]
functions = (root / "projects/ROCKNIX/packages/rocknix/profile.d/001-functions").read_text()
get_setting = re.search(r"^function get_setting\(\) \{\n.*?^\}\n", functions, re.M | re.S)[0]


def game_governor(cfg_text, device_default="performance", platform="ports", rom="Olduvai.sh"):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = pathlib.Path(tmp) / "system.cfg"
        cfg.write_text(cfg_text)
        script = (f'J_CONF={cfg}\nVERBOSE=false\n{get_setting}\n'
                  f'DEVICE_GAME_CPU_GOVERNOR="{device_default}"\nPLATFORM="{platform}"\nROMNAME="/r/{rom}"\n'
                  f'{block}echo "$CPU_GOVERNOR"\n')
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout.strip()


menu = "system.cpugovernor=schedutil\n"
assert game_governor(menu) == "performance", "games run performance while the menu runs schedutil"
assert game_governor(menu + "ports.cpugovernor=powersave\n") == "powersave", "a per-system choice wins"
assert game_governor(menu + 'ports["Olduvai.sh"].cpugovernor=schedutil\n') == "schedutil", "a per-game choice wins"
assert game_governor(menu, device_default="") == "schedutil", "without the device default: upstream behaviour"

RATE_60 = "60.015000"
RATE_NATIVE = "85.019409"
assert abs(float(RATE_60) - 54_000_000 / (1395 * 645)) < 1e-5
assert abs(float(RATE_NATIVE) - 74_250_000 / (1354 * 645)) < 1e-5
rate = re.search(r'^video_refresh_rate = "([0-9.]+)"$', retroarch.read_text(), re.M)[1]
assert rate == RATE_60, rate


def refresh(param, rate):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        cfg = tmp / "retroarch.cfg"
        cfg.write_text(f'video_driver = "gl"\nvideo_refresh_rate = "{rate}"\n')
        (tmp / "param").write_text(param + "\n")
        script = (refresh_quirk.read_text()
                  .replace("/storage/.config/retroarch/retroarch.cfg", str(cfg))
                  .replace("/sys/module/panel_a12/parameters/refresh_60hz", str(tmp / "param")))
        subprocess.run(["sh", "-c", script], check=True, env={"PATH": "/usr/bin:/bin"})
        text = cfg.read_text()
        assert 'video_driver = "gl"' in text, text
        return re.search(r'^video_refresh_rate = "([0-9.]+)"$', text, re.M)[1]


assert refresh("Y", RATE_NATIVE) == RATE_60
assert refresh("Y", RATE_60) == RATE_60
assert refresh("N", RATE_60) == RATE_NATIVE
assert refresh("N", RATE_NATIVE) == RATE_NATIVE
assert refresh("Y", "59.940000") == "59.940000"  # the user's own rate stays
built_cfg = root / "build.ROCKNIX-RK3128.arm/image/system/usr/config/system/configs/system.cfg"
if built_cfg.is_file():
    assert "system.cpugovernor=schedutil" in built_cfg.read_text().splitlines(), "built image lacks the menu governor"
print("a12 game defaults: ok")
