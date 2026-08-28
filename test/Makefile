# Makefile
# See https://docs.cocotb.org/en/stable/quickstart.html for more info

# defaults
SIM ?= icarus
FST ?= -fst # Use more efficient FST format
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src
PROJECT_SOURCES = *.v

ifneq ($(GATES),yes)

# RTL simulation:
SIM_BUILD				= sim_build/rtl
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))

else

# Gate level simulation:
SIM_BUILD				= sim_build/gl
COMPILE_ARGS    += -DGL_TEST
COMPILE_ARGS    += -DFUNCTIONAL
COMPILE_ARGS    += -DSIM
COMPILE_ARGS    += -DNO_SPECIFY
COMPILE_ARGS    += -gno-specify

STDCELL_ORIG = $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog/sg13g2_stdcell.v
STDCELL_PATCHED = $(SIM_BUILD)/sg13g2_stdcell_patched.v

# Execute inline shell patch prior to simulator invocation
PATCH_CMD := $(shell mkdir -p $(SIM_BUILD) && \
	if [ -f "$(STDCELL_ORIG)" ]; then \
		python3 $(PWD)/patch_ihp_delayed_signals.py "$(STDCELL_ORIG)" > "$(STDCELL_PATCHED).tmp" && \
		sed -i '/specify/,/endspecify/d' "$(STDCELL_PATCHED).tmp" && \
		mv "$(STDCELL_PATCHED).tmp" "$(STDCELL_PATCHED)"; \
	fi)

VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_io/verilog/sg13g2_io.v
VERILOG_SOURCES += $(STDCELL_PATCHED)
VERILOG_SOURCES += $(PWD)/gate_level_netlist.v

endif

# Allow sharing configuration between design and testbench via `include`:
COMPILE_ARGS 		+= -I$(SRC_DIR)

# Include the testbench sources:
VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL = tb

# List test modules to run (cocotb uses MODULE):
MODULE = test

# include cocotb's make rules to take care of the simulator setup
include $(shell cocotb-config --makefiles)/Makefile.sim
