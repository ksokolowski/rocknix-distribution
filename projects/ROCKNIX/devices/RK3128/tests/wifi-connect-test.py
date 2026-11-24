#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify real launcher failures and saved-PSK retries without Wi-Fi hardware."""
import json
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
source = (root / "projects/ROCKNIX/packages/rocknix/sources/scripts/wifictl").read_text()
functions = source[source.index("wait_for_wifi() {"):source.index("# Command Router")]

with tempfile.TemporaryDirectory(prefix="a12-wifi-connect-") as temporary:
    directory = pathlib.Path(temporary)
    mock = directory / "nmcli"
    log = directory / "calls.jsonl"
    mock.write_text('''#!/usr/bin/env python3
import json, os, pathlib, stat, sys
args = sys.argv[1:]
record = {"args": list(args)}
if "password" in record["args"]:
    record["args"][record["args"].index("password") + 1] = "[redacted]"
if "passwd-file" in args:
    path = pathlib.Path(args[args.index("passwd-file") + 1])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text() == "802-11-wireless-security.psk:" + os.environ["SAVED_PSK"] + "\\n"
    record["password_file"] = str(path)
with open(os.environ["MOCK_LOG"], "a") as out:
    out.write(json.dumps(record) + "\\n")
if "--show-secrets" in args:
    print(os.environ["SAVED_PSK"])
elif "802-11-wireless.ssid" in args:
    print("ExampleNet")
elif "802-11-wireless.hidden" in args:
    print(os.environ["HIDDEN"])
elif "SSID" in args:
    calls = [json.loads(line) for line in pathlib.Path(os.environ["MOCK_LOG"]).read_text().splitlines()]
    scans = sum("SSID" in call["args"] for call in calls)
    if scans > int(os.environ["SCAN_READY_AFTER"]):
        print("ExampleNet")
elif args[-2:] == ["dev", "status"]:
    print("wlan0:disconnected")
elif "modify" in args:
    sys.exit(int(os.environ["MODIFY_RESULT"]))
elif "connect" in args or "up" in args:
    sys.exit(int(os.environ["ACTIVATE_RESULT"]))
''')
    mock.chmod(0o755)

    def run(command, activate=0, modify=0, saved="", entered="", hidden=False, scan_ready_after=0):
        log.write_text("")
        script = functions + '\nwait_for_wifi() { :; }\nsleep() { :; }\n' + command
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                                env={"PATH": os.environ["PATH"], "NMCLI": str(mock),
                                     "WIFI_DEV": "wlan0", "TARGET_SSID": "ExampleNet",
                                     "TARGET_PSK": entered, "SAVED_PSK": saved,
                                     "ACTIVATE_RESULT": str(activate), "MODIFY_RESULT": str(modify),
                                     "HIDDEN": "yes" if hidden else "no",
                                     "SCAN_READY_AFTER": str(scan_ready_after),
                                     "MOCK_LOG": str(log)})
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        assert not result.stdout and not result.stderr, result.stderr
        for call in calls:
            if "password_file" in call:
                assert not pathlib.Path(call["password_file"]).exists(), "Remove secrets after success/failure"
        return result.returncode, calls

    result, calls = run("connect_wifi", activate=7, entered="synthetic-test-key")
    assert result == 7, "A successful PSK flag update must not hide the handshake failure"
    assert any("modify" in call["args"] for call in calls), "Still persist PSK flags"
    assert run("connect_wifi", modify=1, entered="synthetic-test-key")[0] == 0

    # Include shell metacharacters/colon/backslash to verify literal secret delivery.
    secret = "synthetic:$`key\\value"
    for status in (0, 7):
        result, calls = run('connect_saved_network "ExampleNet"', activate=status, saved=secret)
        assert result == status
        assert any("password_file" in call for call in calls), "Answer iwd's repeated secret request"
        assert all(secret not in call["args"] for call in calls), "Do not put saved PSKs in argv"
        assert not any("delete" in call["args"] for call in calls), "Retain saved profile on failure"

    result, calls = run('connect_saved_network "Open network"')
    assert result == 0 and not any("password_file" in call for call in calls)
    assert run('connect_saved_network "ExampleNet"', activate=10)[0] == 10

    result, calls = run('connect_saved_network "ExampleNet"', saved=secret, scan_ready_after=2)
    assert result == 0
    scans = [i for i, call in enumerate(calls) if "SSID" in call["args"]]
    up = next(i for i, call in enumerate(calls) if "up" in call["args"])
    assert len(scans) == 3 and max(scans) < up, "Wait for the AP to appear before activation"
    assert any("rescan" in call["args"] for call in calls)
    for hidden, ready in ((True, 100), (False, 0)):
        result, calls = run('connect_saved_network "ExampleNet"', hidden=hidden, scan_ready_after=ready)
        assert result == 0 and not any("rescan" in call["args"] for call in calls)
    assert run('connect_saved_network "ExampleNet"', activate=10, scan_ready_after=100)[0] == 10

print("Wi-Fi activation status, saved credential retry, scan readiness and private-file cleanup: OK")
