#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-netwatch logs samples, snapshots bad network states and only reads.

A sample starts at most one process per interface (`ip` for the IPv4
address, which no file shows) plus a gateway ping every third sample: the
counters, memory, pressure and the default route are read with the shell's
own `read` and the loop waits with `read -t`. Every new process keeps
schedutil at its highest clock (2026-10-28: about 60 per minute before).
"""
import os
import pathlib
import re
import shutil
import signal
import subprocess
import time
import tempfile

script = pathlib.Path(__file__).resolve().parents[1] / "packages/a12-controls/sources/a12-netwatch"

FAKES = {
    # ip: addresses and the default route come from control files; any
    # configuring subcommand would be recorded and fails the test.
    "ip": """#!/bin/sh
echo "ip $*" >> "$CALLS"
case "$*" in
  "-4 -o addr show dev eth0") [ -s "$CTL/address" ] && echo "2: eth0    inet $(cat "$CTL/address") brd 192.0.2.255 scope global eth0\\       valid_lft forever preferred_lft forever" ;;
  *) echo "ip output" ;;
esac
exit 0
""",
    "ping": '#!/bin/sh\necho "ping $*" >> "$CALLS"\n[ "$(cat "$CTL/ping")" = ok ]\n',
    "nmcli": '#!/bin/sh\necho "nmcli $*" >> "$CALLS"\necho "nmcli output"\n',
    "ethtool": '#!/bin/sh\necho "ethtool $*" >> "$CALLS"\necho "rx_broadcast: 7"\n',
}
# sleep stops run mode's loop once "$CTL/stop" exists.
FAKES["sleep"] = '#!/bin/sh\n[ -e "$CTL/stop" ] && kill -TERM "$PPID"\nexit 0\n'
for name in ("arping", "dmesg", "journalctl", "systemctl", "iw", "logger", "sync"):
    FAKES[name] = '#!/bin/sh\necho "%s $*" >> "$CALLS"\nexit 0\n' % name


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


with tempfile.TemporaryDirectory(prefix="a12-netwatch-") as temporary:
    root = pathlib.Path(temporary)
    bindir, ctl, out = root / "bin", root / "ctl", root / "out"
    sys, proc = root / "sys", root / "proc"
    for directory in (bindir, ctl, out):
        directory.mkdir()
    for name, text in FAKES.items():
        write(bindir / name, text)
        (bindir / name).chmod(0o755)
    calls = root / "calls"
    pmsg = root / "pmsg"
    environment = dict(
        os.environ,
        PATH=f"{bindir}:/usr/bin:/bin",
        A12_SYS=str(sys),
        A12_PROC=str(proc),
        A12_NETWATCH_DIR=str(out),
        A12_NETWATCH_STATE=str(root / "state"),
        A12_NETWATCH_CONFIG=str(root / "netwatch.conf"),
        A12_KEEPALIVE_CONFIG=str(root / "keepalive.conf"),
        A12_PMSG=str(pmsg),
        CALLS=str(calls),
        CTL=str(ctl),
    )
    write(proc / "sys/kernel/random/boot_id", "boot-a\n")
    write(proc / "interrupts", "           CPU0       CPU1\n 41:        10        20     GIC-0  11 Level     ehci_hcd:usb2\n")
    write(proc / "meminfo", "MemTotal: 250000 kB\nMemAvailable: 90000 kB\n")
    write(proc / "pressure/memory", "some avg10=1.50 avg60=0 avg300=0 total=1\nfull avg10=0.25 avg60=0 avg300=0 total=1\n")
    write(proc / "net/arp", "IP address HW type Flags HW address Mask Device\n")
    write(sys / "class/net/lo/carrier", "1\n")
    eth = sys / "class/net/eth0"
    (eth / "device").mkdir(parents=True)
    write(eth / "urbnum", "500\n")
    write(eth / "operstate", "up\n")
    write(eth / "carrier_changes", "2\n")
    for counter in ("tx_packets", "rx_errors", "rx_dropped", "tx_errors", "tx_dropped"):
        write(eth / "statistics" / counter, "0\n")
    write(ctl / "address", "192.0.2.10/24")
    # Default route 192.0.2.1 via eth0, as /proc/net/route lists it.
    write(proc / "net/route", "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
          "eth0\t00000000\t010200C0\t0003\t0\t0\t100\t00000000\t0\t0\t0\n"
          "eth0\t000200C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0\n")
    write(ctl / "ping", "ok")
    log = out / "boot-a.log"

    def sample(uptime, carrier="1", rx=None):
        write(proc / "uptime", f"{uptime}.42 1.00\n")
        if (eth / "operstate").exists():
            write(eth / "carrier", carrier + "\n")
            write(eth / "statistics/rx_packets", f"{uptime if rx is None else rx}\n")
        result = subprocess.run(["bash", str(script), "sample"], env=environment, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert result.stderr == "", result.stderr

    def snapshots():
        return sorted(path.name for path in out.glob("boot-a-*.txt"))

    # A healthy sample: one line, no snapshot; loopback is not listed.
    sample(100)
    first = log.read_text().splitlines()[0]
    assert first.startswith("100 eth0:c=1,o=up,chg=2,rx=100,"), first
    assert "urb=500,ip=192.0.2.10/24" in first and "ehci=30 mem=90000 psi=1.50/0.25 gw=-" in first, first
    assert " lo:" not in first and snapshots() == []

    # Carrier lost: an immediate snapshot, then one after 60 s, then recovery.
    sample(110, carrier="0")
    assert snapshots() == ["boot-a-110.txt"], snapshots()
    snapshot = (out / "boot-a-110.txt").read_text()
    assert "reasons: carrier:eth0" in snapshot and "== USB devices" in snapshot, snapshot[:300]
    assert "# 110 bad: carrier:eth0" in log.read_text()
    sample(120, carrier="0")
    assert snapshots() == ["boot-a-110.txt"]
    sample(170, carrier="0")
    assert snapshots() == ["boot-a-110.txt", "boot-a-170.txt"], snapshots()
    sample(180)
    assert "# 180 recovered after 70 s" in log.read_text()
    assert "a12-netwatch boot-a 110 bad: carrier:eth0" in pmsg.read_text()

    # Address lost while the link stays up.
    write(ctl / "address", "")
    sample(190)
    assert "# 190 bad: noip:eth0" in log.read_text()
    write(ctl / "address", "192.0.2.10/24")
    sample(200)

    # Receive counter frozen for 60 s on a link that had traffic.
    for uptime in range(210, 280, 10):
        sample(uptime, rx=999)
    assert "rxstall:eth0" in log.read_text(), log.read_text()
    sample(280)

    # Gateway unanswered on three pings (every third sample).
    write(ctl / "ping", "fail")
    for uptime in range(290, 390, 10):
        sample(uptime)
    assert "bad: gateway" in log.read_text(), log.read_text()
    write(ctl / "ping", "ok")
    for uptime in range(390, 420, 10):
        sample(uptime)
    assert log.read_text().count("recovered") == 4, log.read_text()

    # The adapter disappears.
    for path in sorted(eth.rglob("*"), reverse=True):
        path.rmdir() if path.is_dir() else path.unlink()
    eth.rmdir()
    sample(430)
    assert "bad: missing:eth0" in log.read_text()
    write(proc / "uptime", "440.00 1.00\n")

    # One snapshot at the start of each episode (and one after 60 s above).
    assert snapshots() == ["boot-a-110.txt", "boot-a-170.txt", "boot-a-190.txt", "boot-a-270.txt",
                           "boot-a-370.txt", "boot-a-430.txt"], snapshots()

    # Diagnostics only: nothing that configures the network was called.
    for call in calls.read_text().splitlines():
        words = call.split()
        if words[0] == "ip":
            assert not {"set", "del", "flush", "add", "change", "replace"} & set(words), call
        if words[0] == "nmcli":
            assert not {"up", "down", "connect", "disconnect", "reapply", "modify", "delete", "level"} & set(words), call
        if words[0] == "ethtool":
            assert not {"-s", "--set-eee", "-K", "-G", "-r"} & set(words), call
        assert words[0] != "systemctl" or "show" in words or "--failed" in words, call

    # Run mode with NetworkManager debug logging configured: one sample,
    # then the loop waits 10 s and timeout ends it.
    write(root / "netwatch.conf", 'NM_DEBUG="1"\n')
    calls.write_text("")
    result = subprocess.run(["timeout", "3", "bash", str(script), "run"], env=environment, capture_output=True, text=True)
    assert result.returncode == 124 and result.stderr == "", (result.returncode, result.stderr)
    assert "nmcli general logging level INFO domains DEFAULT,CORE:DEBUG" in calls.read_text(), calls.read_text()
    assert "# 440 started" in log.read_text() and "# 440 NetworkManager debug logging on" in log.read_text()
    (root / "netwatch.conf").unlink()

    # Run mode under strace, sampling every 0.5 s: at most the `ip` for eth0
    # per sample and a ping every third one.
    if shutil.which("strace"):
        rebuilt = sys / "class/net/eth0"
        (rebuilt / "device").mkdir(parents=True)
        for name, text in (("urbnum", "500"), ("operstate", "up"), ("carrier", "1"), ("carrier_changes", "2")):
            write(rebuilt / name, text + "\n")
        for counter in ("rx_packets", "tx_packets", "rx_errors", "rx_dropped", "tx_errors", "tx_dropped"):
            write(rebuilt / "statistics" / counter, "0\n")
        trace = root / "trace"
        before = log.read_text().count("\n")
        p = subprocess.Popen(["strace", "-f", "-qq", "-e", "trace=clone,clone3,fork,vfork,execve", "-o", str(trace),
                              "bash", str(script), "run"], env=dict(environment, A12_NETWATCH_INTERVAL="0.5"),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        try:
            time.sleep(4)
        finally:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait(timeout=5)
        samples = log.read_text().count("\n") - before - 1
        lines = trace.read_text().splitlines()
        # Only what the script itself starts; the fake ip and ping are
        # shell scripts with children of their own.
        main = lines[0].split()[0]
        children = [m.group(1) for l in lines if l.split()[0] == main
                    for m in [re.search(r"\b(?:clone3?|v?fork)\(.*= (\d+)$", l)] if m]
        command = {l.split()[0]: re.search(r'execve\("([^"]*)"', l).group(1).rsplit("/", 1)[-1]
                   for l in lines if 'execve("' in l}
        started = [command.get(c, "?") for c in children]
        # Once at start-up and on events: the directory, pruning, the FIFO, notes.
        once = {"mkdir", "touch", "ls", "tail", "mkfifo", "rm", "logger"}
        assert "mkfifo" in started, started
        polling = [c for c in started[started.index("mkfifo") + 1:] if c not in once]
        assert samples >= 4, samples
        assert set(polling) <= {"ip", "ping"}, started
        assert polling.count("ip") <= samples + 1 and polling.count("ping") <= samples // 3 + 1, (started, samples)

    # Retention: the five newest boots' logs and snapshots stay.
    for index in range(7):
        old = out / f"old-{index}.log"
        old.write_text("x\n")
        (out / f"old-{index}-100.txt").write_text("x\n")
        os.utime(old, (1000 + index, 1000 + index))
    os.utime(log, (5000, 5000))
    result = subprocess.run(["sh", str(script), "prune"], env=environment)
    assert result.returncode == 0
    kept = sorted(path.name for path in out.glob("*.log"))
    assert kept == ["boot-a.log", "old-3.log", "old-4.log", "old-5.log", "old-6.log"], kept
    assert not (out / "old-2-100.txt").exists() and (out / "old-6-100.txt").exists()
# The image ships it, enabled (it was hot-installed on the A12 before).
package = (script.parents[1] / "package.mk").read_text()
assert 'cp "${PKG_BUILD}/a12-netwatch" "${INSTALL}/usr/bin/"' in package, "a12-netwatch is installed"
assert "a12-netwatch.service" in package and "enable_service a12-netwatch.service" in package, "and enabled"
assert script.read_text().startswith("#!/bin/bash\n")
print("netwatch: ok")
