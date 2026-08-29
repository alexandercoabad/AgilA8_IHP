# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

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


CLOCK_PERIOD_PS = 15624


def gpio_dir_setup_words():
    return [
        itype('ADDI', 6, 0, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 25), # r6 = 0xF2
        itype('ADDI', 7, 0, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 38), # r7 = 0xFF
        itype('SW', 7, 6, 0),     # GPIO_DIR = 0xFF
    ]


def gpio_data_out_r3_words():
    return [
        itype('ADDI', 6, 0, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 23),
        itype('SW', 3, 6, 0),
    ]


def gpio_data_out_r5_words():
    return [
        itype('ADDI', 6, 0, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 31),
        itype('ADDI', 6, 6, 23),
        itype('SW', 5, 6, 0),
    ]


def gpio_data_out_r5_words_clean():
    return [
        itype('ADDI', 7, 0, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 31),
        itype('ADDI', 7, 7, 23),
        itype('SW', 5, 7, 0),
    ]


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_PS, units="ps").start())


async def reset_dut(dut):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in_reg.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 200)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 20)


def get_signal_val(signal_handle):
    try:
        val = signal_handle.value
        if val.is_resolvable:
            return int(val)
        return None
    except (AttributeError, ValueError):
        return None


def get_halted(dut):
    for path in [
        getattr(getattr(getattr(dut, 'user_project', None), 'core', None), 'halted', None),
        getattr(getattr(dut, 'core', None), 'halted', None)
    ]:
        val = get_signal_val(path)
        if val == 1:
            return True

    val = get_signal_val(dut.uo_out)
    if val is not None:
        return bool(val & 0x80)

    return False


def poke_fmem(dut, byte_addr, value):
    dut.fmem[byte_addr].value = value


def load_flash_image(dut, words, base=0):
    for i, b in enumerate(words_to_bytes(words)):
        poke_fmem(dut, base + i, b)


async def wait_halted(dut, max_cycles=400_000):
    for cyc in range(max_cycles):
        await RisingEdge(dut.clk)
        if get_halted(dut):
            return cyc + 1
    raise TimeoutError(f"design never halted within {max_cycles} cycles")


def reg(dut, n):
    if n == 0:
        return 0

    core_up = getattr(getattr(dut, 'user_project', None), 'core', None)
    core_top = getattr(dut, 'core', None)

    for core in [core_up, core_top]:
        if core is not None:
            regfile = getattr(core, 'regfile', None)
            if regfile is not None:
                regs = getattr(regfile, 'regs', None)
                if regs is not None:
                    val = get_signal_val(regs[n])
                    if val is not None:
                        return val

    return None


def pc(dut):
    for path in [
        getattr(getattr(getattr(dut, 'user_project', None), 'core', None), 'pc', None),
        getattr(getattr(dut, 'core', None), 'pc', None)
    ]:
        val = get_signal_val(path)
        if val is not None:
            return val

    return None


GPIO_HOLD_CYCLES = 150


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

    await ClockCycles(dut.clk, 100)

    prog_words = [
        itype('ADDI', 1, 0, 5),
        itype('ADDI', 2, 0, 3),
        rtype('ADD', 3, 1, 2),
    ] + gpio_dir_setup_words() + gpio_data_out_r3_words() + [
        itype('HALT', 0, 0, 0),
    ]

    prog = words_to_bytes(prog_words)

    await send_byte_gpio(dut, len(prog))
    for b in prog:
        await send_byte_gpio(dut, b)
    await set_gpio(dut, 0, 0, 0)

    await wait_halted(dut)

    uo_val = int(dut.uo_out.value)
    assert (uo_val & 0x0F) == 8, f"External output uo_out[3:0] should be 8, got {uo_val & 0x0F}"


@cocotb.test()
async def test_boundary_continuity(dut):
    """Executes code straddling the 0x0100 IMEM boundary."""
    await start_clock(dut)

    setup = gpio_dir_setup_words()
    words = setup + [
        itype('ADDI', 6, 0, 0),
        itype('ADDI', 6, 6, 1)
    ]

    bytes_so_far = len(words) * 2
    pad_bytes_needed = 0x80 - bytes_so_far
    assert pad_bytes_needed >= 0 and pad_bytes_needed % 2 == 0
    words += [itype('NOP', 0, 0, 0)] * (pad_bytes_needed // 2)

    words += [
        itype('ADDI', 5, 0, 17),
        itype('HALT', 0, 0, 0)
    ]

    load_flash_image(dut, words)
    await reset_dut(dut)

    cycles = await wait_halted(dut)
    assert cycles < 35_000, f"Execution took {cycles} cycles."


@cocotb.test()
async def test_flash_regression(dut):
    """Executes ALU operations and PSRAM read/writes from Flash."""
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
    ] + gpio_dir_setup_words() + gpio_data_out_r5_words() + [
        itype('HALT', 0, 0, 0),
    ]

    load_flash_image(dut, prog)
    await reset_dut(dut)

    cycles = await wait_halted(dut)
    uo_val = int(dut.uo_out.value) & 0x7F
    assert uo_val == 0x7F, f"External output uo_out[6:0]={uo_val}, expected 127"


RAW_REGRESSION_WORDS = [
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
    0x2240, 0x2240, 0xa2be, 0x9ebe
]

FULL_REGRESSION_WORDS = (
    gpio_dir_setup_words() + 
    RAW_REGRESSION_WORDS + 
    gpio_data_out_r5_words_clean() + 
    [itype('HALT', 0, 0, 0)]
)


@cocotb.test()
async def test_full_opcode_regression(dut):
    """Executes every ISA opcode from external Flash."""
    await start_clock(dut)

    load_flash_image(dut, FULL_REGRESSION_WORDS)
    dut.ui_in.value = 0
    await reset_dut(dut)

    await ClockCycles(dut.clk, 25_000)

    dut.ui_in.value = 0x55

    cycles = await wait_halted(dut)
    uo_val = int(dut.uo_out.value) & 0x7F
    assert uo_val == 66, f"External output uo_out[6:0]={uo_val}, expected 66 (0x42)"
