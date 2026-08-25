# Sample testbench for a Tiny Tapeout project

This is a sample testbench for a Tiny Tapeout project. It uses [cocotb](https://docs.cocotb.org/en/stable/) to drive the DUT and check the outputs.
See below to get started or for more information, check the [website](https://tinytapeout.com/hdl/testing/).

## Setting up

1. Edit [Makefile](Makefile) and modify `PROJECT_SOURCES` to point to your Verilog files.
2. Edit [tb.v](tb.v) and replace `tt_um_example` with your module name.

## How to run

To run the RTL simulation:

```sh
make -B
```

To run gatelevel simulation, first harden your project and copy `../runs/wokwi/results/final/verilog/gl/{your_module_name}.v` to `gate_level_netlist.v`.

Then run:

```sh
make -B GATES=yes
```

## How to view the VCD file

Using GTKWave
```sh
gtkwave tb.vcd tb.gtkw
```

Using Surfer
```sh
surfer tb.vcd
```

## What these tests actually check

`test.py` has four cocotb tests, run automatically by `test.yaml`'s
GitHub Actions workflow (`make` in this directory) - this is what "the
design passed CI" actually verifies, as opposed to the stock smoke test
this template ships with by default:

- **`test_bootloader`** - bit-bangs a small program in over GPIO
  through `boot_rom`, with the QSPI Pmod never touched at all, and
  checks it lands in `shared_ram` correctly and executes correctly.
- **`test_boundary_continuity`** - the regression for the flash-address
  discontinuity bug at IMEM 0x0100 (see `tt_um_agila8.v`'s `flash_addr`
  comment) - checks the final PC precisely, not just register values,
  since a wrapped/re-executed run can coincidentally produce the same
  register values as a correct one for some program shapes.
- **`test_flash_regression`** - a small ALU + PSRAM write/readback
  program, run via `boot_rom`'s timeout -> `FLASH_MODE` handoff.
- **`test_full_opcode_regression`** - every opcode, forward and
  backward branches, `JAL`/`JALR` with a negative immediate, memory
  read/write, and GPIO, also run via the timeout -> flash path. This
  program's embedded words were fixed once already for an absolute-vs-
  relative addressing assumption that stopped being true when
  `FLASH_MODE`'s runtime base moved from `0x0000` to `0x0080` - see the
  comment above `FULL_REGRESSION_WORDS` in `test.py` if you're touching
  that program's assembly or the flash base address again.

`tb.v` hosts the flash/PSRAM behavioral model directly (ported from
`tb_regression.v`) - cocotb tests poke `dut.fmem[...]`/`dut.pmem[...]`
before releasing reset rather than driving the SPI protocol bit-by-bit
from Python, which is both simpler and reuses a model already checked
against this exact design elsewhere in this project's history.

The standalone `tb_bootloader.v` / `tb_regression.v` / `tb_boundary.v`
/ `tb_debug_full.v` / `tb_diag_full.v` files are useful for fast local
iteration with plain `iverilog`+`vvp` (each is self-contained and
`$display`s its own pass/fail) - but CI never runs them; only
`test.py` does. `disasm.py` is a standalone helper for reading
assembled instruction words back out as mnemonics, handy when a test
in this suite fails and you need to know what the CPU was actually
about to execute.
