#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-button-test: each press with its label, code and RetroArch/ES mapping (test 62).

Owner request 2026-10-13 after X/Y were found swapped in the mapping files:
a small tool that shows, for every button pressed, the device-tree label
(= the printed label), the key code, the joystick button number and what
RetroArch (stick.cfg) and ES (es_input.cfg) map it to, flagging mismatches.
Run against a fake /proc/device-tree, mapping files and canned evtest output.
"""
import os
import pathlib
import struct
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
script = root / "projects/ROCKNIX/devices/RK3128/packages/a12-controls/sources/a12-button-test"
KEYS = {"a": 304, "b": 305, "x": 307, "y": 308, "l": 310, "r": 311, "select": 314, "start": 315, "back": 316,
        "up": 544, "volume-up": 115}

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    for label, code in KEYS.items():
        node = tmp / "proc/device-tree/stick" / label
        node.mkdir(parents=True)
        (node / "label").write_bytes(label.encode() + b"\0")
        (node / "linux,code").write_bytes(struct.pack(">I", code))
    (tmp / "proc/device-tree/stick/compatible").write_bytes(b"gpio-keys-polled\0")
    joypad = tmp / "stick.cfg"
    # X/Y deliberately swapped, as before the fix; A/B positional (test 73).
    joypad.write_text('input_device = "stick"\ninput_a_btn = "1"\ninput_b_btn = "0"\ninput_y_btn = "2"\n'
                      'input_x_btn = "3"\ninput_l_btn = "4"\ninput_r_btn = "5"\ninput_select_btn = "6"\n'
                      'input_start_btn = "7"\ninput_enable_hotkey_btn = "8"\ninput_up_btn = "9"\n')
    es = tmp / "es_input.cfg"
    es.write_text('<inputList><inputConfig type="joystick" deviceName="stick" deviceGUID="1">'
                  '<input name="a" type="button" id="0" value="1"/><input name="x" type="button" id="2" value="1"/>'
                  '<input name="y" type="button" id="3" value="1"/><input name="pageup" type="button" id="4" value="1"/>'
                  '</inputConfig></inputList>\n')
    bindir = tmp / "bin"
    bindir.mkdir()
    events = "".join(f"Event: time 1.0, type 1 (EV_KEY), code {c} (X), value {v}\n"
                     for c in (307, 308, 304, 115, 310) for v in (1, 0))
    (bindir / "evtest").write_text(f"#!/bin/sh\ncat <<'E'\n{events}E\n")
    (bindir / "evtest").chmod(0o755)
    (tmp / "devname").write_text("stick\n")
    env = dict(os.environ, A12_ROOT=str(tmp), A12_JOYPAD=str(joypad), A12_ES_INPUT=str(es),
               A12_BUTTON_EVENT_DEV="/dev/input/event0", PATH=f"{bindir}:/usr/bin:/bin")
    out = subprocess.run(["sh", str(script), "5"], env=env, capture_output=True, text=True, check=True).stdout
    lines = [l.split() for l in out.splitlines() if " code " in f" {l} "]
    by = {l[0]: l for l in lines}
    assert set(by) == {"x", "y", "a", "volume-up", "l"}, out
    assert by["x"][1:4] == ["code", "307", "btn"] and by["x"][4] == "2", out
    # X pressed: RetroArch maps button 2 to y (swapped) -> flagged; ES says x -> fine.
    assert "RetroArch: y" in " ".join(by["x"]) and "ES: x" in " ".join(by["x"]) and "<--" in " ".join(by["x"]), out
    # Printed A is RetroPad B (position, like a Nintendo pad's left button): fine.
    assert "RetroArch: b" in " ".join(by["a"]) and "<--" not in " ".join(by["a"]), out
    assert "RetroArch: l" in " ".join(by["l"]) and "ES: pageup" in " ".join(by["l"]) and "<--" not in " ".join(by["l"]), out
    assert by["volume-up"][1:3] == ["code", "115"] and "btn" not in by["volume-up"], out
print("button test: ok")
