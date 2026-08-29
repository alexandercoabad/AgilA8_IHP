# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0
#
# Runs bootloader test in both RTL and Gate-Level (GL) simulation modes.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

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


# 15624 ps (~64MHz clock speed).
CLOCK_PERIOD_PS = 15624

# Extended hold cycle margin for stable signal transitions in GL simulation
GPIO_HOLD_CYCLES = 500


# Helper sequence to configure GPIO_DIR = 0xFF (address 0xF2) using r6 and r7
# Bit 7 must be 1 so that HALT status can reach uo_out[7] in GL mode
def gpio_dir_setup_words():
    return [
        # Build r6 = 0xF2 (242)
        itype('ADDI', 6, 0, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 25),
        # Build r7 = 0xFF (255)
        itype('ADDI', 7, 0, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 38),
        # Store r7 (0xFF) to [r6] (0xF2)
        itype('SW', 7, 6, 0),
    ]


# Helper sequence to emit register value in r3 out to GPIO_DATA (0xF0)
def gpio_data_out_r3_words():
    return [
        itype('ADDI', 6, 0, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 23),  # r6 = 0xF0 (GPIO_DATA)
        itype('SW', 3, 6, 0),      # Write r3 to [0xF0]
    ]


# ---------------------------------------------------------------------
# Helper Utilities & Hierarchy Accessors
# ---------------------------------------------------------------------

async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_PS, units="ps").start())


async def reset_dut(dut):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 20)
    await Timer(1, units="ns")


def get_halted(dut):
    """Safely checks HALT state in RTL across hierarchy levels and GL mode."""
    for path in [("user_project", "core"), ("core",)]:
        try:
            scope = dut
            for attr in path:
                scope = getattr(scope, attr)
            return int(scope.halted.value) == 1
        except (AttributeError, ValueError):
            pass

    # Top-level pin check fallback for Gate-Level mode
    if hasattr(dut, "uo_out") and dut.uo_out.value.is_resolvable:
        try:
            val = int(dut.uo_out.value)
            return (val & 0x80) != 0
        except ValueError:
            pass

    return False


async def wait_halted(dut, max_cycles=600_000):
    """Waits until execution halts safely across RTL and GL environments."""
    for cyc in range(max_cycles):
        await RisingEdge(dut.clk)
        # Allow gate delays and non-blocking assignments to settle
        await Timer(1, units="ns")
        if get_halted(dut):
            return cyc + 1
    raise TimeoutError(f"design never halted within {max_cycles} cycles")


def reg(dut, n):
    """Safely retrieves register values, returning None if running in GL mode."""
    if n == 0:
        return 0
    for path in [("user_project", "core", "regfile"), ("core", "regfile")]:
        try:
            scope = dut
            for attr in path:
                scope = getattr(scope, attr)
            return int(scope.regs[n].value)
        except (AttributeError, ValueError):
            pass
    return None


# ---------------------------------------------------------------------
# Test 1: Bootloader over GPIO
# ---------------------------------------------------------------------

async def set_gpio(dut, data, clock, start):
    dut.ui_in.value = (int(start) << 2) | (int(clock) << 1) | int(data)


async def send_bit(dut, bit):
    await set_gpio(dut, bit, 0, 1)
    await ClockCycles(dut.clk, GPIO_HOLD_CYCLES)
    await set_gpio(dut, bit, 1, 1)
    await ClockCycles(dut.clk, GPIO_HOLD_CYCLES)
    await set_gpio(dut, bit, 0, 1)
    await ClockCycles(dut.clk, GPIO_HOLD_CYCLES)


async def send_byte_gpio(dut, byte):
    for i in range(7, -1, -1):
        await send_bit(dut, (byte >> i) & 1)


@cocotb.test()
async def test_bootloader(dut):
    """Bit-bangs a program into shared_ram over ui_in[0:2] using boot_rom."""
    await start_clock(dut)
    await reset_dut(dut)

    # Initial state: start bit asserted (ui_in[2] = 1)
    await set_gpio(dut, 0, 0, 1)
    await ClockCycles(dut.clk, 100)

    # Program payload: configure GPIO DIR, load r1=5, r2=3, r3=8, emit to GPIO DATA, halt
    prog_words = gpio_dir_setup_words() + [
        itype('ADDI', 1, 0, 5),
        itype('ADDI', 2, 0, 3),
        rtype('ADD', 3, 1, 2),    # r3 = 5 + 3 = 8
    ] + gpio_data_out_r3_words() + [
        itype('HALT', 0, 0, 0),
    ]

    prog = words_to_bytes(prog_words)

    # Send length byte followed by instructions
    await send_byte_gpio(dut, len(prog))
    for b in prog:
        await send_byte_gpio(dut, b)

    # Keep start bit asserted (ui_in[2] = 1) so execution transitions to RAM cleanly
    await set_gpio(dut, 0, 0, 1)

    await wait_halted(dut)

    if reg(dut, 1) is not None:
        assert reg(dut, 1) == 5, f"r1 should be 5, got {reg(dut, 1)}"
        assert reg(dut, 2) == 3, f"r2 should be 3, got {reg(dut, 2)}"
        assert reg(dut, 3) == 8, f"r3 should be 8, got {reg(dut, 3)}"

    assert dut.uo_out.value.is_resolvable, "uo_out contains unresolvable X/Z states"
    uo_val = int(dut.uo_out.value)
    assert (uo_val & 0x0F) == 8, f"External output uo_out[3:0] should be 8, got {uo_val & 0x0F}"
