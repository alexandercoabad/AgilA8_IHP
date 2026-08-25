import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

import sys
sys.path.insert(0, '.')
from asm_selfcheck import PASS_SENTINEL, FAIL_SENTINEL
from build_selfcheck_programs import build_boundary_test

CLOCK_PERIOD_NS = 1000.0 / 64.0


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_NS, units="ns").start())


async def reset_dut(dut):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)


def poke_fmem(dut, byte_addr, value):
    dut.fmem[byte_addr].value = value


def load_flash_image(dut, data, base=0):
    for i, b in enumerate(data):
        poke_fmem(dut, base + i, b)


@cocotb.test()
async def measure_boundary_correct(dut):
    """How many cycles does the CORRECT (single-pass) boundary test
    take to reach its GPIO sentinel?"""
    await start_clock(dut)
    load_flash_image(dut, build_boundary_test())
    await reset_dut(dut)

    cyc = 0
    for _ in range(2_000_000):
        await RisingEdge(dut.clk)
        cyc += 1
        low7 = int(dut.uo_out.value) & 0x7F
        if low7 == PASS_SENTINEL:
            dut._log.info(f"CORRECT boundary test: PASS sentinel at cycle {cyc}")
            return
        if low7 == FAIL_SENTINEL:
            raise AssertionError(f"FAIL sentinel at cycle {cyc} (unexpected)")
    raise TimeoutError(f"never reached sentinel within {cyc} cycles")


@cocotb.test()
async def measure_wait_start_timeout(dut):
    """How many cycles does boot_rom's WAIT_START loop take to time out
    and reach flash execution, when no START is ever asserted? Measured
    indirectly via a trivial flash program that immediately writes a
    GPIO sentinel - so the measured cycle count is
    (WAIT_START timeout duration) + (a few instructions' worth)."""
    await start_clock(dut)
    from asm_selfcheck import Asm
    a = Asm()
    a.gpio_write(1, PASS_SENTINEL)
    a.HALT()
    load_flash_image(dut, a.to_bytes())
    await reset_dut(dut)

    cyc = 0
    for _ in range(2_000_000):
        await RisingEdge(dut.clk)
        cyc += 1
        low7 = int(dut.uo_out.value) & 0x7F
        if low7 == PASS_SENTINEL:
            dut._log.info(f"WAIT_START timeout + trivial flash prog: sentinel at cycle {cyc}")
            return
    raise TimeoutError(f"never reached sentinel within {cyc} cycles")
