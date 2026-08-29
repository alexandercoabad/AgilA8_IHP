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
    
    # Redefine source files to load the gate-level netlist and PDK Verilog models
    VERILOG_SOURCES = $(TEST_DIR)/tb.v
    VERILOG_SOURCES += $(TEST_DIR)/gate_level_netlist.v
    VERILOG_SOURCES += /home/runner/pdk/ihp-sg13g2/libs.ref/sg13g2_io/verilog/sg13g2_io.v
    VERILOG_SOURCES += /home/runner/pdk/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog/sg13g2_stdcell.v
endif

# Include cocotb makefiles
include $(shell cocotb-config --makefiles)/Makefile.sim
