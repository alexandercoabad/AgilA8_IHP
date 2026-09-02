# Makefile for Cocotb testing (RTL & Gate-Level Simulation)

SIM ?= icarus
TOPLEVEL_LANG ?= verilog

# Paths
SRC_DIR = $(PWD)/../src
TEST_DIR = $(PWD)

# Standard cocotb setup
TOPLEVEL = tb
MODULE = test

# Verilog Source Files for RTL
VERILOG_SOURCES += $(TEST_DIR)/tb.v
VERILOG_SOURCES += $(SRC_DIR)/tt_um_agila8.v
VERILOG_SOURCES += $(SRC_DIR)/a8_core.v
VERILOG_SOURCES += $(SRC_DIR)/a8_alu.v
VERILOG_SOURCES += $(SRC_DIR)/a8_peripherals.v
VERILOG_SOURCES += $(SRC_DIR)/a8_regfile.v
VERILOG_SOURCES += $(SRC_DIR)/boot_rom.v
VERILOG_SOURCES += $(SRC_DIR)/shared_ram.v
VERILOG_SOURCES += $(SRC_DIR)/qspi_shared_engine.v

# Icarus Verilog Flags
# -gno-specify disables specify blocks to avoid library timing construct errors in GL
COMPILE_ARGS += -g2012 -gno-specify -I$(SRC_DIR)

# Gate-Level Simulation Configuration
ifeq ($(GATES),yes)
    COMPILE_ARGS += -DGL_TEST -DFUNCTIONAL -DSIM

    PDK_ROOT ?= /home/runner/pdk
    STDCELL_SRC     := $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog/sg13g2_stdcell.v
    STDCELL_PATCHED := $(TEST_DIR)/sg13g2_stdcell.functional.v

    # *** BUG FIX (see chat / gatelevel_test_results): IHP's
    # sg13g2_stdcell.v routes every sequential cell's real CLK/D/RESET_B
    # through internal `delayed_*` wires that are only ever driven via
    # the "delayed output" arguments of $setuphold/$recrem/$width timing
    # checks inside each cell's `specify` block (see
    # patch_ihp_delayed_signals.py's docstring for the full mechanism).
    # Icarus Verilog does not implement that mechanism - confirmed by the
    # "sorry: ifnone with an edge-sensitive path is not supported"
    # warnings emitted from those exact specify blocks - so with the raw
    # PDK file, delayed_* floats and EVERY flip-flop in the netlist reads
    # X forever, independent of anything this project's RTL does. Traced
    # directly in a failing GL run's VCD: core.imem_valid/dmem_valid and
    # the FSM state register all collapse to X within 2 clock cycles of
    # reset release, and not one bit of shared_ram or the register file
    # is ever written for the rest of the simulation - the bootloader
    # test then times out waiting for a HALT that can never happen.
    #
    # test.yaml (RTL-only `make`, GATES unset) already patches this in a
    # separate CI step, but that step only touches $PDK_ROOT and doesn't
    # run for whatever job invokes `GATES=yes make` (e.g. Tiny Tapeout's
    # own gate-level-test workflow, which isn't a file in this repo and
    # so can't be edited here) - so that patch never applied to the GL
    # path specifically. Doing it here instead, inline in the Makefile,
    # means it's applied automatically for GATES=yes regardless of which
    # workflow/job calls `make`, and it writes to a local copy under
    # test/ rather than mutating the shared $PDK_ROOT file (avoids
    # permissions issues and any risk of interfering with other jobs
    # that might read the same PDK checkout concurrently).
    $(shell python3 $(TEST_DIR)/patch_ihp_delayed_signals.py $(STDCELL_SRC) > $(STDCELL_PATCHED).tmp \
        && sed -i '/specify/,/endspecify/d' $(STDCELL_PATCHED).tmp \
        && mv $(STDCELL_PATCHED).tmp $(STDCELL_PATCHED))

    # Redefine source files to load the gate-level netlist and PDK Verilog models
    VERILOG_SOURCES = $(TEST_DIR)/tb.v
    VERILOG_SOURCES += $(TEST_DIR)/gate_level_netlist.v
    VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_io/verilog/sg13g2_io.v
    VERILOG_SOURCES += $(STDCELL_PATCHED)
endif

# Include cocotb makefiles
include $(shell cocotb-config --makefiles)/Makefile.sim
