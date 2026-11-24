#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""a12-release-audit stops a public release that ships something it should not.

Each check gets a planted problem in a small system tree: a game or BIOS
file outside the content list, a known commercial BIOS by checksum, a large
unlisted data file, a private identifier, a private key, a developer login
other than the shared one; release notes with an AI note or a private
identifier; an update tar whose checksum no hardware test names. A clean
tree, with a listed free game and text files that only look like ROMs by
their extension (README.md), passes.
"""
import hashlib
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[5]
tool = root / "projects/ROCKNIX/devices/RK3128/tools/a12-release-audit"
content = root / "projects/ROCKNIX/devices/RK3128/release-content.tsv"
assert content.is_file(), "the content list is versioned with the code"


def audit(tree, *extra, private="lan.example\nfalcon-home\n", notes=None, testlog=None):
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        (t / "private").write_text(private)
        args = ["python3", str(tool), "--tree", str(tree), "--private", str(t / "private"),
                "--content", str(content), *extra]
        if notes is not None:
            (t / "notes.md").write_text(notes)
            args += ["--notes", str(t / "notes.md")]
        if testlog is not None:
            (t / "TEST_LOG.md").write_text(testlog)
            args += ["--testlog", str(t / "TEST_LOG.md")]
        r = subprocess.run(args, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


def tree_with(files):
    t = pathlib.Path(tempfile.mkdtemp())
    base = {
        "usr/share/a12-free-games/gb/Tobu Tobu Girl.gb": b"\x00\xc3\x50\x01" + bytes(300),
        "usr/share/doc/README.md": b"# Notes\nplain text\n",
        "usr/bin/tool": b"\x7fELF" + bytes(64) + b"devid=jelos&devpassword=jelos",
        # Broadcom Wi-Fi nvram files name the chip with devid= (test 103): not a login.
        # ssh, NetworkManager and GnuTLS carry the PEM header as text to parse keys (test 103).
        # GnuTLS's public self-test keys (crypto-selftests-pk.c), listed with key: (test 103).
        "usr/lib/libgnutls.so.30.42.0": b"\x7fELF" + b"-----BEGIN EC PRIVATE KEY-----\n" + b"MHcCAQEEIPAKWV7pZe9c5EubMNfAEKWRQtPMvlO9HehwHmJssNoAo" + b"\n",
        "usr/sbin/sshd": b"\x7fELF" + bytes(32) + b"-----BEGIN OPENSSH PRIVATE KEY-----\x00%s\x00",
        "usr/lib/firmware/brcm/brcmfmac43340-sdio.txt": b"boardtype=0x0b0c\ndevid=0x4386\n",
    }
    base.update(files)
    for rel, data in base.items():
        p = t / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return t


code, out = audit(tree_with({}))
assert code == 0, f"a clean tree passes:\n{out}"

cases = {
    "unlisted ROM": {"usr/share/stuff/game.sfc": bytes(1024)},
    "BIOS by name": {"usr/share/stuff/scph1001.bin": bytes(1024)},
    "large unlisted data": {"usr/share/stuff/blob.dat": os.urandom(3 * 1024 * 1024)},
    "private identifier": {"usr/share/doc/setup.txt": b"server at lan.example\n"},
    "private key": {"etc/ssh/key": b"-----BEGIN OPENSSH PRIVATE KEY-----\n" + b"b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ" * 2 + b"\n"},
    "another developer login": {"usr/bin/other": b"\x7fELF" + b"devid=someone&devpassword=x"},
}
for name, files in cases.items():
    code, out = audit(tree_with(files))
    assert code != 0 and "FAIL" in out, f"{name} must fail the audit:\n{out}"

bios = b"pretend this is a console BIOS"
code, out = audit(tree_with({"usr/share/misc/data.bin": bios}),
                  "--extra-bad-sha1", hashlib.sha1(bios).hexdigest())
assert code != 0 and "known BIOS" in out, f"a known BIOS checksum fails wherever it sits:\n{out}"

code, out = audit(tree_with({}), notes="Built with help from an AI assistant.\n")
assert code != 0 and "notes" in out, f"an AI note in the release notes fails:\n{out}"
code, out = audit(tree_with({}), notes="Copy it from falcon-home.\n")
assert code != 0 and "notes" in out, f"a private identifier in the notes fails:\n{out}"
code, out = audit(tree_with({}), notes="Faster boots and lighter music.\n")
assert code == 0, f"plain notes pass:\n{out}"

with tempfile.TemporaryDirectory() as tmp:
    tar = pathlib.Path(tmp) / "release.tar"
    tar.write_bytes(b"pretend update")
    sha = hashlib.sha256(tar.read_bytes()).hexdigest()
    (pathlib.Path(tmp) / "release.tar.sha256").write_text(f"{sha}  release.tar\n")
    code, out = audit(tree_with({}), "--tar-checksum-only", str(tar), testlog="| 1 | other image `deadbeef…` |\n")
    assert code != 0 and "tested" in out, f"an update tar no hardware test names fails:\n{out}"
    code, out = audit(tree_with({}), "--tar-checksum-only", str(tar), testlog=f"| 1 | update tar `{sha[:8]}…` |\n")
    assert code == 0, f"a tested update tar passes:\n{out}"
    (pathlib.Path(tmp) / "release.tar.sha256").write_text(f"{'0' * 64}  release.tar\n")
    code, out = audit(tree_with({}), "--tar-checksum-only", str(tar), testlog=f"| 1 | update tar `{sha[:8]}…` |\n")
    assert code != 0 and "checksum" in out, f"a .sha256 that does not match fails:\n{out}"

code, out = audit(tree_with({"usr/lib/libother.so": b"\x7fELF" + b"-----BEGIN EC PRIVATE KEY-----\n" + b"MHcCAQEEIPAKWV7pZe9c5EubMNfAEKWRQtPMvlO9HehwHmJssNoAo" + b"\n"}))
assert code != 0 and "private key" in out, f"a key outside the key: lines fails:\n{out}"


# The export: a private doc path may appear only with upstream's own content
# (ROCKNIX ships an AGENTS.md of its own, test 103); ours, or another, fails.
def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()


with tempfile.TemporaryDirectory() as tmp:
    t = pathlib.Path(tmp)
    src, pub = t / "src", t / "pub"
    for r in (src, pub):
        r.mkdir()
        git(r, "init", "-q", "-b", "main")
        git(r, "config", "user.email", "a@b")
        git(r, "config", "user.name", "a")
    (src / "AGENTS.md").write_text("upstream rules\n")
    (src / "code.c").write_text("int a;\n")
    git(src, "add", "-A"); git(src, "commit", "-q", "-m", "base"); git(src, "branch", "upstream")
    (src / "AGENTS.md").write_text("our private rules\n")
    (src / "code.c").write_text("int a = 1;\n")
    git(src, "commit", "-q", "-am", "ours"); git(src, "branch", "release")

    def export(agents):
        (pub / "AGENTS.md").write_text(agents)
        (pub / "code.c").write_text("int a = 1;\n")
        git(pub, "add", "-A"); git(pub, "commit", "-q", "--allow-empty", "-m", "export"); git(pub, "branch", "-f", "port")
        return audit(tree_with({}), "--export-repo", str(pub), "--export-ref", "port", "--source-repo", str(src),
                     "--source-rev", "release", "--upstream-rev", "upstream")

    code, out = export("upstream rules\n")
    assert code == 0, f"upstream's own AGENTS.md in the export passes:\n{out}"
    code, out = export("our private rules\n")
    assert code != 0 and "AGENTS.md" in out, f"our AGENTS.md in the export fails:\n{out}"

print("release audit: ok")
