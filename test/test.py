# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0
#
# Runs bootloader test in both RTL and Gate-Level (GL) simulation modes.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

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


# 15624 ps (~64MHz clock speed). Uses an even integer so period / 2 (7812 ps)
# fits cleanly into 1ps simulator precision without floating-point errors.
CLOCK_PERIOD_PS = 15624


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
        itype('ADDI', 6, 6, 23), # r6 = 0xF0 (GPIO_DATA)
        itype('SW', 3, 6, 0),     # Write r3 to [0xF0]
    ]


# Helper sequence to emit register value in r5 out to GPIO_DATA (0xF0)
def gpio_data_out_r5_words():
    return [
        itype('ADDI', 6, 0, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 23), # r6 = 0xF0 (GPIO_DATA)
        itype('SW', 5, 6, 0),     # Write r5 to [0xF0]
    ]


# Clean helper sequence to emit r5 out to GPIO_DATA (0xF0) using r7 instead of r6
def gpio_data_out_r5_words_clean():
    return [
        itype('ADDI', 7, 0, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 23), # r7 = 0xF0 (GPIO_DATA)
        itype('SW', 5, 7, 0),     # Store r5 (66) to 0xF0
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
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)


def get_halted(dut):
    """Safely checks HALT state in RTL across hierarchy levels and GL mode."""
    try:
        return int(dut.user_project.core.halted.value) == 1
    except (AttributeError, ValueError):
        pass

    try:
        return int(dut.core.halted.value) == 1
    except (AttributeError, ValueError):
        pass

    try:
        val = int(dut.uo_out.value)
        return (val & 0x80) != 0
    except ValueError:
        return False


def poke_fmem(dut, byte_addr, value):
    dut.fmem[byte_addr].value = value


def load_flash_image(dut, words, base=0):
    """Pokes an assembled program into the flash behavioral model in tb.v."""
    for i, b in enumerate(words_to_bytes(words)):
        poke_fmem(dut, base + i, b)


async def wait_halted(dut, max_cycles=400_000):
    """Waits until execution halts safely across RTL and GL environments."""
    for cyc in range(max_cycles):
        await RisingEdge(dut.clk)
        if get_halted(dut):
            return cyc + 1
    raise TimeoutError(f"design never halted within {max_cycles} cycles")


def reg(dut, n):
    """Safely retrieves register values, returning None if running in GL mode."""
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
    """Safely retrieves program counter value, returning None in GL mode."""
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

GPIO_HOLD_CYCLES = 200


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

    uo_val = int(dut.uo_out.value)
    assert (uo_val & 0x0F) == 8, f"External output uo_out[3:0] should be 8, got {uo_val & 0x0F}"
