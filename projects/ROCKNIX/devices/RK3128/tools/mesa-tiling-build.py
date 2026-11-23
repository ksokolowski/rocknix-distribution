#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the focused benchmark from an already configured Mesa source tree."""

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mesa", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--host", action="store_true")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    if args.sanitize and not args.host:
        parser.error("--sanitize requires --host")
    mesa = args.mesa.resolve()
    build = (args.build_dir or mesa / ".armv7ve-rocknix-linux-gnueabi").resolve()
    source = Path(__file__).with_name("mesa-tiling-bench.c").resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.host:
        command = ["cc", "-std=c11", "-O3", "-Wall", "-Wextra",
                   "-ffunction-sections", "-fdata-sections",
                   "-DHAVE_ENDIAN_H", "-DHAVE_STRUCT_TIMESPEC",
                   "-DUSE_GCC_ATOMIC_BUILTINS", "-DHAVE___BUILTIN_UNREACHABLE",
                   "-DHAVE___BUILTIN_CLZ", "-DHAVE___BUILTIN_CLZLL",
                   "-DHAVE___BUILTIN_CTZ", "-DHAVE___BUILTIN_CTZLL"]
        command += [f"-I{p}" for p in (mesa / "src/panfrost/shared", mesa / "src",
                                      mesa / "include", build / "src")]
        if args.sanitize:
            command += ["-O1", "-g", "-fsanitize=address,undefined",
                        "-fno-omit-frame-pointer"]
    else:
        # Reuse the actual package flags, including the Cortex-A7 tuning.
        entries = json.loads((build / "compile_commands.json").read_text())
        entry = next(e for e in entries if e["file"].endswith("/pan_tiling.c"))
        original = shlex.split(entry["command"])
        command = []
        skip = False
        for token in original:
            if skip:
                skip = False
                continue
            if token in ("-o", "-MF", "-MQ", "-MT", "-c"):
                skip = True
            elif token not in ("-MD", "-MMD"):
                command.append(token)
    command += [str(source), "-Wl,--gc-sections", "-lm", "-o", str(output)]
    subprocess.run(command, cwd=build, check=True)
    provenance = {
        "scope": "actual Mesa aligned/generic inner kernels; no driver, GPU or presentation",
        "host": args.host,
        "sanitized": args.sanitize,
        "command": command,
        "files": {},
    }
    for path in (source, mesa / "src/panfrost/shared/pan_tiling.c",
                 mesa / "src/panfrost/shared/pan_tiling.h", output):
        provenance["files"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    output.with_name(output.name + ".json").write_text(
        json.dumps(provenance, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
