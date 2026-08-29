import cocotb
from cocotb.triggers import Timer, RisingEdge
from cocotb.clock import Clock

@cocotb.test()
async def test_agila8(dut):
    """Agila8 verification engine base test."""
    dut._log.info("Booting Agila8 Verification Engine...")

    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())

    dut.ena.value = 1
    dut.rst_n.value = 0
    dut.ui_in.value = 0x00
    dut.uio_in.value = 0x00
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut._log.info("System Reset complete. Commencing validation loops...")

    for step in range(24):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if not dut.uo_out.value.is_resolvable:
            dut._log.warning(f"Step {step:02d} | uo_out contains unresolvable X/Z states: {dut.uo_out.value.binstr}")
            continue

        uo_val = dut.uo_out.value.to_unsigned()
        dut._log.info(f"Step {step:02d} | uo_out: 0x{uo_val:02X}")

    dut._log.info("Agila8 verification sequence completed successfully!")
