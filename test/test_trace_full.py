import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

import sys
sys.path.insert(0, '.')
from asm_selfcheck import PASS_SENTINEL, FAIL_SENTINEL, Asm
from build_selfcheck_programs import build_full_opcode_regression

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
async def trace_full_opcode(dut):
    await start_clock(dut)
    prog = build_full_opcode_regression()
    load_flash_image(dut, prog)
    dut.ui_in.value = 0
    await reset_dut(dut)

    # ui_in=0x55 needs to be set before the GPIO_IN read, but not so
    # early it collides with boot_rom's START bit - use the calibrated
    # WAIT_START timeout (~4432 cycles) with generous margin.
    await ClockCycles(dut.clk, 6000)
    dut.ui_in.value = 0x55

    last_pc = None
    last_state = None
    cyc = 0
    for _ in range(200_000):
        await RisingEdge(dut.clk)
        cyc += 1
        try:
            pc = int(dut.user_project.core.pc.value)
            state = int(dut.user_project.core.state.value)
        except AttributeError:
            pc = None
            state = None
        if pc != last_pc or state != last_state:
            r = [int(dut.user_project.core.regfile.regs[i].value) if pc is not None else -1 for i in range(8)]
            dut._log.info(f"cyc={cyc} pc=0x{pc:04x} state={state} regs={r}")
            last_pc = pc
            last_state = state
        low7 = int(dut.uo_out.value) & 0x7F
        if low7 == PASS_SENTINEL:
            dut._log.info(f"PASS sentinel at cycle {cyc}")
            return
        if low7 == FAIL_SENTINEL:
            dut._log.info(f"FAIL sentinel at cycle {cyc}, pc=0x{pc:04x}")
            return
    dut._log.info(f"TIMEOUT at cycle {cyc}, pc=0x{pc:04x}")
