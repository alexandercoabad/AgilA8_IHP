# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, FallingEdge

# ---------------------------------------------------------------------
# Assembler / Instruction Encoding Helpers
# ---------------------------------------------------------------------

OP = dict(NOP=0, ADD=1, ADDI=2, SUB=3, AND=4, OR=5, XOR=6, SLL=7, SRL=8,
          LW=9, SW=0xA, BEQ=0xB, BLT=0xC, JAL=0xD, JALR=0xE, HALT=0xF)


def itype(op, rd, rs1, imm6):
    return (OP[op] << 12) | (rd << 9) | (rs1 << 6) | (imm6 & 0x3F)


def rtype(op, rd, rs1, rs2):
    return (OP[op] << 12) | (rd << 9) | (rs1 << 6) | (rs2 << 3)


def words_to_bytes(words):
    out = bytearray()
    for w in words:
        out.append((w >> 8) & 0xFF)
        out.append(w & 0xFF)
    return out


CLOCK_PERIOD_NS = 1000.0 / 64.0  # 64MHz clock speed


def gpio_dir_setup_words():
    return [
        itype('ADDI', 6, 0, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 25),
        itype('ADDI', 7, 0, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 4),
        itype('SW', 7, 6, 0),
    ]


# ---------------------------------------------------------------------
# Helper Utilities & Hierarchy Accessors
# ---------------------------------------------------------------------

async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_NS, units="ns").start())


async def reset_dut(dut):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 30)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)


def get_halted(dut):
    """Checks HALT state across standard RTL hierarchy and GL netlist aliases."""
    for path in [
        lambda: dut.user_project.core.halted.value,
        lambda: dut.core.halted.value,
        lambda: dut.user_project.halted.value,
    ]:
        try:
            return int(path()) == 1
        except (AttributeError, ValueError):
            pass

    try:
        uo_val = int(dut.uo_out.value)
        uio_val = int(dut.uio_out.value)
        return bool((uo_val & 0x80) or (uio_val & 0x80))
    except (ValueError, TypeError):
        return False


def poke_fmem(dut, byte_addr, value):
    dut.fmem[byte_addr].value = value


def load_flash_image(dut, words, base=0):
    for i, b in enumerate(words_to_bytes(words)):
        poke_fmem(dut, base + i, b)


async def wait_halted(dut, max_cycles=400_000):
    """Waits until execution halts safely across RTL and GL environments."""
    for _ in range(max_cycles):
        await RisingEdge(dut.clk)
        if get_halted(dut):
            return
    raise TimeoutError(f"design never halted within {max_cycles} cycles")


def reg(dut, n):
    if n == 0:
        return 0
    try:
        return int(dut.user_project.core.regfile.regs[n].value)
    except (AttributeError, ValueError):
        pass

    try:
        return int(dut.core.regfile.regs[n].value)
    except (AttributeError, ValueError):
        return None


def pc(dut):
    try:
        return int(dut.user_project.core.pc.value)
    except (AttributeError, ValueError):
        pass

    try:
        return int(dut.core.pc.value)
    except (AttributeError, ValueError):
        return None


# ---------------------------------------------------------------------
# Test 1: Bootloader over GPIO
# ---------------------------------------------------------------------

async def send_bit(dut, bit):
    # Setup data ahead of clock pulse
    await FallingEdge(dut.clk)
    dut.ui_in.value = (1 << 2) | (0 << 1) | (bit & 1)
    await ClockCycles(dut.clk, 2)

    # Pulse serial clock
    await FallingEdge(dut.clk)
    dut.ui_in.value = (1 << 2) | (1 << 1) | (bit & 1)
    await ClockCycles(dut.clk, 2)

    # Drop serial clock
    await FallingEdge(dut.clk)
    dut.ui_in.value = (1 << 2) | (0 << 1) | (bit & 1)
    await ClockCycles(dut.clk, 2)


async def send_byte_gpio(dut, byte):
    for i in range(7, -1, -1):
        await send_bit(dut, (byte >> i) & 1)


@cocotb.test()
async def test_bootloader(dut):
    """Bit-bangs a program into shared_ram over ui_in[0:2]."""
    await start_clock(dut)
    await reset_dut(dut)

    # Ensure start bit is inactive initially
    await FallingEdge(dut.clk)
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, 10)

    # Assert start signal (ui_in[2] = 1)
    await FallingEdge(dut.clk)
    dut.ui_in.value = 1 << 2
    await ClockCycles(dut.clk, 10)

    prog_words = [
        itype('ADDI', 1, 0, 5),
        itype('ADDI', 2, 0, 3),
        rtype('ADD', 3, 1, 2),
    ] + gpio_dir_setup_words() + [
        itype('HALT', 0, 0, 0),
    ]

    prog = words_to_bytes(prog_words)

    # Send length byte followed by instructions
    await send_byte_gpio(dut, len(prog))
    for b in prog:
        await send_byte_gpio(dut, b)

    # Clear inputs and complete transmission
    await FallingEdge(dut.clk)
    dut.ui_in.value = 0

    await wait_halted(dut)

    if reg(dut, 1) is not None:
        assert reg(dut, 1) == 5, f"r1 should be 5, got {reg(dut, 1)}"
        assert reg(dut, 2) == 3, f"r2 should be 3, got {reg(dut, 2)}"
        assert reg(dut, 3) == 8, f"r3 should be 8, got {reg(dut, 3)}"


# ---------------------------------------------------------------------
# Test 2: Flash Address Boundary Continuity
# ---------------------------------------------------------------------

@cocotb.test()
async def test_boundary_continuity(dut):
    await start_clock(dut)

    setup = gpio_dir_setup_words()
    words = setup + [
        itype('ADDI', 6, 0, 0),
        itype('ADDI', 6, 6, 1)
    ]

    pad_count = 128 - len(words) - 2
    if pad_count > 0:
        words += [itype('NOP', 0, 0, 0)] * pad_count

    words += [
        itype('ADDI', 5, 0, 17),
        itype('HALT', 0, 0, 0)
    ]

    load_flash_image(dut, words)
    await reset_dut(dut)

    await wait_halted(dut)

    if pc(dut) is not None:
        assert reg(dut, 5) == 17, f"r5={reg(dut, 5)}, expected 17"
        assert reg(dut, 6) == 1, f"r6={reg(dut, 6)}, expected 1"


# ---------------------------------------------------------------------
# Test 3: Flash / PSRAM Execution Regression
# ---------------------------------------------------------------------

@cocotb.test()
async def test_flash_regression(dut):
    await start_clock(dut)

    prog = [
        itype('ADDI', 1, 0, 15),
        itype('ADDI', 2, 0, -16),
        rtype('OR', 3, 1, 2),
        itype('ADDI', 4, 0, 31),
        itype('ADDI', 4, 4, 31),
        itype('ADDI', 4, 4, 31),
        itype('ADDI', 4, 4, 31),
        itype('ADDI', 4, 4, 26),
        itype('SW', 3, 4, 0),
        itype('LW', 5, 4, 0),
    ] + gpio_dir_setup_words() + [
        itype('HALT', 0, 0, 0),
    ]

    load_flash_image(dut, prog)
    await reset_dut(dut)

    await wait_halted(dut)

    if reg(dut, 1) is not None:
        assert reg(dut, 1) == 15
        assert reg(dut, 2) == 240
        assert reg(dut, 3) == 255
        assert reg(dut, 4) == 150, f"r4={reg(dut, 4)}, expected 150"
        assert reg(dut, 5) == 255, f"r5={reg(dut, 5)}, expected 255"
        assert int(dut.pmem[150].value) == 255, "PSRAM[150] was never written"


# ---------------------------------------------------------------------
# Test 4: Full All-Opcode Regression
# ---------------------------------------------------------------------

FULL_REGRESSION_WORDS = gpio_dir_setup_words() + [
    0x2202, 0x2240, 0x2240, 0x2240, 0xe476, 0xd005, 0x2e00,
    0x2205, 0x240a, 0x1650, 0x3888, 0x4a50, 0x5a50, 0x6a50, 0x7c42,
    0x8d82, 0x223d, 0x3208, 0x240a, 0xa410, 0x9e10, 0x221f, 0x225f,
    0x225f, 0x2247, 0x241b, 0xa440, 0x9640, 0x2205, 0xb242, 0xf000,
    0x281f, 0x290b, 0x2900, 0x2900, 0x2a03, 0x2c01, 0x2400, 0x3b70,
    0x2481, 0xb142, 0xb03d, 0x2203, 0xc205, 0x261f, 0x26df, 0x26df,
    0x26d2, 0x261f, 0x26df, 0x26cf, 0x26c0, 0x281f, 0x291f, 0x291f,
    0x2912, 0x281f, 0x291f, 0x291a, 0x2900, 0x2a1f, 0x2b5f, 0x2b44,
    0x2b40, 0x2430, 0x2480, 0x2480, 0x2480, 0x2220, 0x2260, 0x226a,
    0x2240, 0xa280, 0x9680, 0x9881, 0x243c, 0x2480, 0x2480, 0x2480,
    0x221f, 0x225f, 0x2242, 0x2240, 0xa280, 0x9c80, 0x2201, 0x2240,
    0x2240, 0x2240, 0xa2be, 0x9ebe, 0xf000,
]


@cocotb.test()
async def test_full_opcode_regression(dut):
    await start_clock(dut)

    load_flash_image(dut, FULL_REGRESSION_WORDS)
    dut.ui_in.value = 0
    await reset_dut(dut)

    try:
        for _ in range(10_000):
            await RisingEdge(dut.clk)
            if int(dut.user_project.flash_mode_r.value) == 1:
                break
    except (AttributeError, ValueError):
        await ClockCycles(dut.clk, 25_000)

    dut.ui_in.value = 0x55

    await wait_halted(dut)

    if reg(dut, 1) is not None:
        assert reg(dut, 1) == 1, f"r1={reg(dut, 1)}, expected 1"
        assert reg(dut, 2) == 252, f"r2={reg(dut, 2)}, expected 252"
        assert reg(dut, 3) == 170, f"r3={reg(dut, 3)}, expected 170"
        assert reg(dut, 4) == 85, f"r4={reg(dut, 4)}, expected 85"
        assert reg(dut, 5) == 66, f"r5={reg(dut, 5)}, expected 66"
        assert reg(dut, 6) == 64, f"r6={reg(dut, 6)}, expected 64"
        assert reg(dut, 7) == 1, f"r7={reg(dut, 7)}, expected 1"
        assert pc(dut) == 0x0152, f"pc=0x{pc(dut):04x}, expected 0x0152"
