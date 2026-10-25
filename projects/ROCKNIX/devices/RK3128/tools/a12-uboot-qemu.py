#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Execute A12 U-Boot with packaged QEMU and a limited RK3128 MMIO model.

This diagnoses CPU startup and SD/extlinux handoff; it is not a hardware
replacement. See packages/u-boot/README.md for prerequisites and limitations.
"""

import argparse, bisect, collections, hashlib, json, socket, struct, subprocess, sys, tempfile, time
from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
from capstone.arm import ARM_OP_MEM


class RSP:
    def __init__(self, sock):
        self.sock = sock

    def send(self, command):
        raw = command.encode()
        self.sock.sendall(b"$" + raw + b"#" + f"{sum(raw)&255:02x}".encode())

    def read_byte(self):
        value = self.sock.recv(1)
        if not value:
            raise ConnectionError("QEMU closed its debug socket")
        return value

    def receive(self):
        while self.read_byte() != b"$":
            pass
        result = bytearray()
        while True:
            c = self.read_byte()
            if c == b"#":
                break
            result.extend(c)
        check = self.read_byte() + self.read_byte()
        assert int(check, 16) == sum(result) & 255
        self.sock.sendall(b"+")
        return result.decode()

    def command(self, command):
        self.send(command)
        return self.receive()

    def memory(self, addr, size):
        return bytes.fromhex(self.command(f"m{addr:x},{size:x}"))

    def write(self, addr, data):
        assert self.command(f"M{addr:x},{len(data):x}:{data.hex()}") == "OK"

    def registers(self):
        raw = bytes.fromhex(self.command("g"))
        self.raw_regs = bytearray(raw)
        return list(struct.unpack("<16I", raw[:64]))

    def setreg(self, reg, value):
        self.raw_regs[reg * 4 : reg * 4 + 4] = struct.pack("<I", value)
        result = self.command("G" + self.raw_regs.hex())
        assert result == "OK", result


class Model:
    def __init__(self, disk=None):
        self.disk = disk.open("rb") if disk else None
        self.fifo = collections.deque()
        self.sd_commands = []
        self.regs = {0x200081CC: 0x10006245, 0x200081D0: 0}
        # Synthetic 256 MiB DDR3: one rank, 14 rows, 10 columns, 16-bit bus.
        self.uart = []
        self.fifo_batches = []
        self.unknown = collections.Counter()
        self.accesses = []

    def read(self, addr, size):
        if 0x10214000 <= addr < 0x10215000:
            off = addr - 0x10214000
            if off == 0x200:
                if not self.fifo:
                    raise RuntimeError("SD FIFO underflow")
                return self.fifo.popleft()
            if off == 0x48:
                return (
                    (min(len(self.fifo), 256) << 17) | (0 if self.fifo else 4) | 0x100
                )
            if off == 0x44:
                return self.regs.get(addr, 0) | (0x28 if self.fifo else 0)
            if off == 0x4C:
                return self.regs.get(addr, 0xFF << 16)
            if off == 0x6C:
                return 0x240A
        if addr & ~0xFFFF in [0x20060000, 0x20064000, 0x20068000]:
            offset = addr & 0xFFF
            if offset == 0x14:
                return 0x60  # THRE + TEMT, no input
            if offset == 0x7C:
                return 2  # transmitter FIFO not full
        if 0x20000000 <= addr < 0x20000040 and addr % 16 == 4:
            # CRU PLL_CON1: active-high lock after powerup.
            value = self.regs.get(addr, 1 | (1 << 6) | (1 << 12))
            return value | (0 if value & (1 << 13) else (1 << 10))
        if addr not in self.regs:
            self.unknown[f"{addr:08x}"] += 1
        return self.regs.get(addr, 0) & ((1 << (8 * size)) - 1)

    def write(self, addr, size, value):
        if 0x10214000 <= addr < 0x10215000:
            off = addr - 0x10214000
            if off == 0:
                if value & 7:
                    self.fifo.clear()
                self.regs[addr] = value & ~7
                return
            if off == 0x80:
                self.regs[addr] = value & ~1
                return
            if off == 0x44:
                self.regs[addr] = self.regs.get(addr, 0) & ~value
                return
            if off == 0x2C:
                self.regs[addr] = value & ~(1 << 31)
                if value & (1 << 21):
                    return
                cmd = value & 63
                arg = self.regs.get(0x10214028, 0)
                self.sd_commands.append(
                    {"command": cmd, "argument": hex(arg), "data": bool(value & 512)}
                )
                self.regs[0x10214044] = 4
                self.regs[0x10214030] = 0x900
                if cmd == 8:
                    self.regs[0x10214030] = arg
                elif cmd == 41:
                    self.regs[0x10214030] = 0xC0FF8000
                elif cmd == 3:
                    self.regs[0x10214030] = 0x12340000
                elif cmd == 1:
                    self.regs[0x10214044] |= 256
                elif cmd in [2, 9]:
                    v = (
                        (1 << 126)
                        | (0x0E << 112)
                        | (0x32 << 96)
                        | (0x5B5 << 84)
                        | (9 << 80)
                        | (255 << 48)
                        | (9 << 22)
                        if cmd == 9
                        else 0x123456789ABCDEF00000000100000100
                    )
                    for i in range(4):
                        self.regs[0x10214030 + 4 * i] = (v >> (32 * i)) & 0xFFFFFFFF
                if value & 512:
                    count = self.regs.get(0x10214020, 0)
                    if cmd in [17, 18]:
                        if not self.disk:
                            raise RuntimeError("SD data requires a fixture file")
                        self.disk.seek(arg * 512)
                        data = self.disk.read(count)
                    elif cmd == 51:
                        data = (0x0105000000000000).to_bytes(8, "big")
                    elif cmd == 13:
                        data = bytes(64)
                    elif cmd == 6:
                        data = bytes(64)
                    else:
                        raise RuntimeError(f"Unsupported SD data command {cmd}")
                    assert len(data) == count, (cmd, len(data), count)
                    self.fifo = collections.deque(
                        struct.unpack("<" + str(len(data) // 4) + "I", data)
                    )
                    self.regs[0x10214044] |= 8
                return
        if addr & ~0xFFFF in [0x20060000, 0x20064000, 0x20068000]:
            base = addr & ~0xFFF
            if addr == base and not self.regs.get(base + 0xC, 0) & 0x80:
                self.uart.append(value & 255)
        if 0x20000000 <= addr < 0x20000200 or 0x20008000 <= addr < 0x20008300:
            mask = value >> 16
            self.regs[addr] = (self.regs.get(addr, 0) & ~mask) | (value & mask)
        else:
            self.regs[addr] = value


class Trace:
    milestones = [
        "board_init_f",
        "dram_init",
        "dram_init_banksize",
        "rockchip_dram_init_banksize_fixup",
        "relocate_code",
        "board_init_r",
        "board_late_init",
        "rk_board_late_init",
        "mmc_initialize",
        "mmc_init",
        "rk3128_clk_probe",
        "hang",
        "panic",
        "undefined_instruction",
        "data_abort",
        "prefetch_abort",
        "boot_jump_linux",
        "boot_prep_linux",
        "main_loop",
    ]

    def __init__(self, args):
        self.args = args
        self.functions = []
        self.syms = {}
        self.reloc = 0
        with args.elf.open("rb") as f:
            elf = ELFFile(f)
            # Avoid pyelftools validating U-Boot’s legacy .hash section (sh_link=0).
            # Read headers directly; instantiate only the valid symbol table.
            headers = [elf._get_section_header(i) for i in range(elf.num_sections())]
            table = elf.get_section(
                next(i for i, h in enumerate(headers) if h["sh_type"] == "SHT_SYMTAB")
            )
            for s in table.iter_symbols():
                self.syms[s.name] = s["st_value"] & ~1
                if s["st_info"]["type"] == "STT_FUNC" and s["st_size"]:
                    self.functions.append(
                        (
                            s["st_value"] & ~1,
                            s["st_size"],
                            bool(s["st_value"] & 1),
                            s.name,
                        )
                    )
            self.functions.sort()
            self.starts = [f[0] for f in self.functions]
            self.sections = []
            for header in headers:
                if header["sh_flags"] & 2 and header["sh_type"] != "SHT_NOBITS":
                    f.seek(header["sh_offset"])
                    self.sections.append((header["sh_addr"], f.read(header["sh_size"])))
        self.arm = Cs(CS_ARCH_ARM, CS_MODE_ARM)
        self.thumb = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        self.arm.detail = self.thumb.detail = True
        self.mmu = []
        self.events = []
        self.breakpoints = {}
        self.model = Model(args.sd_fixture)
        if args.inspect_mmu:
            self.mmu_site, self.table_offset = self.mmu_enable_site()

    def function_at(self, pc):
        pc = pc - self.reloc if self.reloc and pc >= 0x60000000 + self.reloc else pc
        i = bisect.bisect_right(self.starts, pc) - 1
        if i >= 0:
            f = self.functions[i]
            if f[0] <= pc < f[0] + f[1]:
                return f
        return None

    def mmu_enable_site(self):
        """Find SCTLR.M write and preceding gd->arch.tlb_addr load in ELF."""
        function = next(f for f in self.functions if f[3] == "dcache_enable")
        for base, data in self.sections:
            if base <= function[0] < base + len(data):
                code = data[function[0] - base : function[0] - base + function[1]]
                break
        else:
            raise RuntimeError("dcache_enable has no code section")
        decoder = self.thumb if function[2] else self.arm
        table_offset = None
        for ins in decoder.disasm(code, function[0]):
            if ins.mnemonic.startswith("ldr"):
                for operand in ins.operands:
                    if operand.type == ARM_OP_MEM and ins.reg_name(
                        operand.mem.base
                    ) in ["r9", "sb"]:
                        table_offset = operand.mem.disp
            if (
                ins.mnemonic == "mcr"
                and ins.op_str.startswith("p15, #0,")
                and ", c1, c0, #0" in ins.op_str
            ):
                if table_offset is None:
                    raise RuntimeError(
                        "Cannot locate TLB pointer load before SCTLR write"
                    )
                return ins.address, table_offset
        raise RuntimeError("Cannot locate MMU activation in dcache_enable")

    def add_breakpoints(self, offset):
        if self.args.inspect_mmu:
            address = self.mmu_site + offset
            assert self.rsp.command(f"Z0,{address:x},2") == "OK"
            self.breakpoints[address] = "before_mmu_enable"
        for name in self.milestones:
            if name in self.syms:
                addr = self.syms[name] + offset
                assert self.rsp.command(f"Z0,{addr:x},2") == "OK"
                self.breakpoints[addr] = name

    def execute(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        out = self.args.output.resolve()
        out.mkdir(parents=True, exist_ok=True)
        self.args.payload = self.args.payload.resolve()
        cmd = [
            "qemu-system-arm",
            "-M",
            "none",
            "-cpu",
            "cortex-a7",
            "-m",
            "2G",
            "-nodefaults",
            "-nographic",
            "-monitor",
            "none",
            "-serial",
            "none",
            "-S",
            "-qmp",
            f"unix:{out}/qmp.sock,server=on,wait=off",
            "-gdb",
            f"tcp:127.0.0.1:{port}",
            "-device",
            f"loader,file={self.args.payload},addr=0x60000000,cpu-num=0,force-raw=on",
        ]
        self.qemu = subprocess.Popen(
            cmd, stdout=(out / "qemu.txt").open("w"), stderr=subprocess.STDOUT
        )
        client = socket.socket()
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client.settimeout(2)
        for _ in range(100):
            try:
                client.connect(("127.0.0.1", port))
                break
            except OSError:
                client.close()
                client = socket.socket()
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                client.settimeout(2)
                time.sleep(0.02)
        else:
            self.qemu.terminate()
            self.qemu.wait(timeout=5)
            raise RuntimeError("QEMU debug socket did not become available")
        self.rsp = RSP(client)
        self.rsp.command("qSupported")
        self.rsp.command("?")
        # Only the CPU executes in QEMU; these ranges are watched RAM backing
        # synthetic RK3128 register models, not a stock virt board.
        for address, length in [(0x20000000, 0x200000), (0x10000000, 0x300000)]:
            assert self.rsp.command(f"Z4,{address:x},{length:x}") == "OK"
        self.rsp.write(0x200081CC, struct.pack("<I", 0x10006245))
        self.add_breakpoints(0)
        deadline = time.monotonic() + self.args.seconds
        reason = "wall-time limit"
        last = ""
        regs = []
        try:
            for count in range(1000000):
                if time.monotonic() > deadline:
                    break
                self.rsp.send("c")
                try:
                    stop = self.rsp.receive()
                except socket.timeout:
                    client.sendall(b"\x03")
                    stop = self.rsp.receive()
                    reason = "no register/milestone event for 2 s"
                    break
                regs = self.rsp.registers()
                pc = regs[15]
                last = stop
                if "awatch:" in stop:
                    f = self.function_at(pc)
                    decoder = self.thumb if f and f[2] else self.arm
                    ins = next(decoder.disasm(self.rsp.memory(pc, 4), pc))
                    memory = next(op for op in ins.operands if op.type == ARM_OP_MEM)

                    def regnum(identifier):
                        name = ins.reg_name(identifier)
                        return {
                            "sp": 13,
                            "lr": 14,
                            "pc": 15,
                            "sb": 9,
                            "sl": 10,
                            "fp": 11,
                            "ip": 12,
                        }.get(name, int(name[1:]) if name.startswith("r") else -1)

                    base = regs[regnum(memory.mem.base)]
                    if regnum(memory.mem.base) == 15:
                        base = (pc + (4 if f and f[2] else 8)) & ~3
                    addr = base + memory.mem.disp
                    if memory.mem.index:
                        addr += regs[regnum(memory.mem.index)] << memory.shift.value
                    opname = ins.mnemonic.split(".")[0]
                    size = 1 if "b" in opname else 2 if "h" in opname else 4
                    if addr == 0x10214200 and self.args.fast_fifo:
                        # Accelerate only the verified scalar FIFO-copy loop;
                        # command, card, filesystem and boot code still execute.
                        following = list(decoder.disasm(self.rsp.memory(pc, 18), pc))
                        assert [x.mnemonic for x in following[:5]] == [
                            "ldr.w",
                            "dmb",
                            "str",
                            "adds",
                            "b",
                        ], [(x.mnemonic, x.op_str) for x in following]
                        assert (
                            following[0].op_str == "r2, [r2, #0x200]"
                            and following[2].op_str == "r2, [r8], #4"
                        )
                        end = struct.unpack("<I", self.rsp.memory(regs[13] + 8, 4))[0]
                        count = end - regs[1]
                        assert 0 < count <= 256 and count <= len(self.model.fifo), (
                            count,
                            len(self.model.fifo),
                        )
                        words = [self.model.fifo.popleft() for _ in range(count)]
                        data = struct.pack("<" + str(count) + "I", *words)
                        self.rsp.write(regs[8], data)
                        self.rsp.setreg(8, regs[8] + len(data))
                        self.rsp.setreg(1, end)
                        self.rsp.setreg(2, words[-1])
                        target = following[4].operands[0].imm
                        self.rsp.setreg(15, target)
                        self.model.fifo_batches.append(
                            {
                                "bytes": len(data),
                                "destination": hex(regs[8]),
                                "sha256": hashlib.sha256(data).hexdigest(),
                            }
                        )
                        continue
                    region = next(
                        (a, n)
                        for a, n in [(0x20000000, 0x200000), (0x10000000, 0x300000)]
                        if a <= addr < a + n
                    )
                    if opname.startswith("ldr"):
                        value = self.model.read(addr, size)
                        self.rsp.write(addr, value.to_bytes(size, "little"))
                    elif not opname.startswith("str"):
                        raise RuntimeError(
                            f"Unhandled MMIO {ins.mnemonic} {ins.op_str}"
                        )
                    a, n = region
                    assert self.rsp.command(f"z4,{a:x},{n:x}") == "OK"
                    stepped = self.rsp.command("s")
                    assert stepped.startswith("T05") or stepped.startswith(
                        "S05"
                    ), stepped
                    assert self.rsp.command(f"Z4,{a:x},{n:x}") == "OK"
                    if opname.startswith("str"):
                        value = int.from_bytes(self.rsp.memory(addr, size), "little")
                        self.model.write(addr, size, value)
                        self.rsp.write(
                            addr,
                            self.model.regs.get(addr, value).to_bytes(4, "little")[
                                :size
                            ],
                        )
                    if len(self.model.accesses) < 2000:
                        self.model.accesses.append(
                            {
                                "pc": hex(pc),
                                "address": hex(addr),
                                "instruction": ins.mnemonic + " " + ins.op_str,
                                "value": hex(value),
                            }
                        )
                    continue
                if pc in self.breakpoints:
                    name = self.breakpoints.pop(pc)
                    self.rsp.command(f"z0,{pc:x},2")
                    event = {
                        "name": name,
                        "pc": hex(pc),
                        "r0": hex(regs[0]),
                        "r1": hex(regs[1]),
                        "r2": hex(regs[2]),
                        "r9": hex(regs[9]),
                    }
                    self.events.append(event)
                    print(json.dumps(event), flush=True)
                    if name == "before_mmu_enable":
                        table = struct.unpack(
                            "<I", self.rsp.memory(regs[9] + self.table_offset, 4)
                        )[0]
                        ptes = {
                            hex(i): hex(
                                struct.unpack("<I", self.rsp.memory(table + i * 4, 4))[
                                    0
                                ]
                            )
                            for i in [
                                0x600,
                                0x683,
                                0x684,
                                0x691,
                                0x692,
                                0x693,
                                0x6FE,
                                0x6FF,
                            ]
                        }
                        mmu = {
                            "table": hex(table),
                            "pte": ptes,
                            "patch": self.args.patch_final_bank,
                        }
                        self.mmu.append(mmu)
                        print(json.dumps(mmu), flush=True)
                        if self.args.patch_final_bank:
                            self.rsp.write(
                                table + 0x6FF * 4, struct.pack("<I", 0x6FF00C0E)
                            )
                    if name == "boot_jump_linux":
                        if self.args.expected_kernel:
                            self.dump_memory(
                                out,
                                0x62000000,
                                self.args.expected_kernel.stat().st_size,
                                "loaded-kernel.bin",
                            )
                            actual = hashlib.sha256(
                                (out / "loaded-kernel.bin").read_bytes()
                            ).hexdigest()
                            expected = hashlib.sha256(
                                self.args.expected_kernel.read_bytes()
                            ).hexdigest()
                            assert actual == expected, (actual, expected)
                            self.events.append(
                                {
                                    "name": "loaded_kernel_sha256_verified",
                                    "sha256": actual,
                                    "bytes": self.args.expected_kernel.stat().st_size,
                                }
                            )
                        address = 0x62000000
                        assert self.rsp.command(f"Z0,{address:x},4") == "OK"
                        self.breakpoints[address] = "kernel_entry"
                    if name == "kernel_entry":
                        if regs[0] != 0:
                            raise RuntimeError("Linux r0 must be zero")
                        header = self.rsp.memory(regs[2], 8)
                        magic, size = struct.unpack(">II", header)
                        if magic != 0xD00DFEED or not 40 <= size <= 1024 * 1024:
                            raise RuntimeError("Invalid handoff FDT header")
                        self.dump_memory(out, regs[2], size, "handoff.dtb")
                        self.events.append(
                            {
                                "name": "handoff_fdt_saved",
                                "address": hex(regs[2]),
                                "bytes": size,
                            }
                        )
                        reason = "Linux kernel entry reached"
                        break
                    if name in [
                        "hang",
                        "panic",
                        "undefined_instruction",
                        "data_abort",
                        "prefetch_abort",
                    ]:
                        reason = "fatal " + name
                        break
                    if name == "relocate_code":
                        self.reloc = regs[0] - 0x60000000
                        self.add_breakpoints(self.reloc)
                else:
                    reason = "unexpected stop " + stop
                    break
            else:
                reason = "event count limit"
        except Exception as e:
            import traceback

            traceback.print_exc()
            reason = f"{type(e).__name__}: {e}"
        finally:
            try:
                regs = self.rsp.registers()
            except Exception:
                pass
            self.qemu.terminate()
            try:
                self.qemu.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.qemu.kill()
                self.qemu.wait()
            client.close()
            if self.model.disk:
                self.model.disk.close()
        report = {
            "reason": reason,
            "last_stop": last,
            "pc": hex(regs[15]) if regs else None,
            "function": self.function_at(regs[15]) if regs else None,
            "qemu_version": subprocess.check_output(
                ["qemu-system-arm", "--version"], text=True
            ).splitlines()[0],
            "fast_fifo": self.args.fast_fifo,
            "sd_fixture_sha256": (
                hashlib.sha256(self.args.sd_fixture.read_bytes()).hexdigest()
                if self.args.sd_fixture
                else None
            ),
            "payload_sha256": hashlib.sha256(
                self.args.payload.read_bytes()
            ).hexdigest(),
            "mmu": self.mmu,
            "milestones": self.events,
            "uart": bytes(self.model.uart).decode("ascii", errors="replace"),
            "fifo_batches": self.model.fifo_batches,
            "sd_commands": self.model.sd_commands,
            "unknown_register_reads": dict(self.model.unknown),
            "mmio": self.model.accesses,
            "assumptions": [
                "Synthetic GRF geometry encoding 256 MiB; not captured hardware state",
                "UART transmitter ready; no RX",
                "PLL lock immediate after powerup",
                "RAM scaffold spans 2 GiB to back watched MMIO and real DDR addresses",
                "Only one CPU; no TEE, IRQ, display or analogue timing model",
                "SDHC PIO model with synthetic 128 MiB FAT fixture and saved A12 boot files",
            ],
        }
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        (out / "uart.txt").write_text(report["uart"])
        print(report["reason"])
        print(report["uart"])
        return 0 if reason == "Linux kernel entry reached" else 1

    def dump_memory(self, out, address, size, name):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as qmp:
            qmp.settimeout(5)
            qmp.connect(str(out / "qmp.sock"))
            with qmp.makefile("rwb", buffering=0) as stream:
                json.loads(stream.readline())
                for command in [
                    {"execute": "qmp_capabilities"},
                    {
                        "execute": "human-monitor-command",
                        "arguments": {
                            "command-line": f'pmemsave 0x{address:x} {size} "{out/name}"'
                        },
                    },
                ]:
                    stream.write((json.dumps(command) + "\n").encode())
                    while True:
                        result = json.loads(stream.readline())
                        if "event" not in result:
                            break
                    if "error" in result:
                        raise RuntimeError(result)
        if (out / name).stat().st_size != size:
            raise RuntimeError("Incomplete memory dump")


def create_fixture(boot_root, disk):
    """Build a sparse 128 MiB, MBR/FAT32 fixture without mounting or root."""
    files = [
        "KERNEL",
        "device_trees/rk3128-powkiddy-a12-rev-a.dtb",
        "extlinux/extlinux.conf",
    ]
    for name in files:
        if not (boot_root / name).is_file():
            raise FileNotFoundError(boot_root / name)
    if disk.exists():
        raise FileExistsError(f"Refusing to overwrite fixture {disk}")
    disk.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="a12-qemu-fat-", dir=disk.parent) as temp:
        fat = Path(temp) / "fat.img"
        with fat.open("wb") as stream:
            stream.truncate(112 * 1024 * 1024)
        subprocess.run(["mkfs.fat", "-F", "32", "-n", "ROCKNIX", str(fat)], check=True)
        subprocess.run(
            ["mmd", "-i", str(fat), "::/device_trees", "::/extlinux"], check=True
        )
        for name in files:
            subprocess.run(
                ["mcopy", "-i", str(fat), str(boot_root / name), "::/" + name],
                check=True,
            )
        mbr = bytearray(512)
        mbr[446:462] = struct.pack(
            "<B3sB3sII", 0, b"\xfe\xff\xff", 0x0C, b"\xfe\xff\xff", 32768, 229376
        )
        mbr[510:512] = b"\x55\xaa"
        with disk.open("xb") as stream, fat.open("rb") as partition:
            stream.truncate(128 * 1024 * 1024)
            stream.write(mbr)
            stream.seek(16 * 1024 * 1024)
            while data := partition.read(1024 * 1024):
                stream.write(data)
    manifest = {
        "origin": "Synthetic SD fixture, never written to hardware",
        "files": {
            name: {
                "path": str(boot_root / name),
                "bytes": (boot_root / name).stat().st_size,
                "sha256": hashlib.sha256((boot_root / name).read_bytes()).hexdigest(),
            }
            for name in files
        },
    }
    disk.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path, help="Unstripped U-Boot ELF with symbols")
    parser.add_argument(
        "payload",
        type=Path,
        help="Matching raw u-boot-dtb.bin, not packed LOADER image",
    )
    parser.add_argument(
        "output", type=Path, help="Directory for UART log, report and memory dumps"
    )
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument(
        "--expected-kernel", type=Path, help="Verify loaded bytes against this kernel"
    )
    parser.add_argument(
        "--sd-fixture", type=Path, help="Read-only synthetic 128 MiB SD image"
    )
    parser.add_argument(
        "--create-fixture-from",
        type=Path,
        help="Create absent --sd-fixture from saved boot tree",
    )
    parser.add_argument(
        "--fast-fifo",
        action="store_true",
        help="Accelerate verified GCC13 FIFO copy loop; recorded in report",
    )
    parser.add_argument(
        "--inspect-mmu",
        action="store_true",
        help="Inspect bank descriptors at MMU activation",
    )
    parser.add_argument(
        "--patch-final-bank",
        action="store_true",
        help="DIAGNOSTIC ONLY: override final bank PTE; never use to validate a build",
    )
    args = parser.parse_args()
    if args.patch_final_bank and not args.inspect_mmu:
        parser.error("--patch-final-bank requires --inspect-mmu")
    if args.create_fixture_from:
        if not args.sd_fixture:
            parser.error("--create-fixture-from requires --sd-fixture")
        create_fixture(args.create_fixture_from, args.sd_fixture)
    return Trace(args).execute()


if __name__ == "__main__":
    sys.exit(main())
