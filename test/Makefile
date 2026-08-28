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
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_io/verilog/sg13g2_io.v

# --- WORKAROUND -----------------------------------------------------
# IHP's sg13g2_stdcell.v routes every sequential cell's real CLK/D/
# RESET_B through internal `delayed_*` wires that are only driven via
# the "delayed output" arguments of $setuphold/$recrem/$width timing-
# check system tasks in each cell's specify block. Icarus Verilog does
# not implement that mechanism ("Timing checks are not supported and
# delayed signal ... will not be driven"), so those wires float
# permanently, resolve to X, and every flip-flop/latch in the design
# reads X forever regardless of what the design actually does -
# independent of anything in this project. This patches the PDK's
# copy at build time with a direct pass-through (safe for a
# -DFUNCTIONAL-only sim, where timing accuracy isn't being checked
# anyway) instead of modifying the PDK install itself.
sim_build/gl/sg13g2_stdcell.functional.v: $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog/sg13g2_stdcell.v
	@mkdir -p sim_build/gl
	python3 patch_ihp_delayed_signals.py $< > $@

VERILOG_SOURCES += sim_build/gl/sg13g2_stdcell.functional.v
# ---------------------------------------------------------------------

# this gets copied in by the GDS action workflow
VERILOG_SOURCES += $(PWD)/gate_level_netlist.v

endif

# Allow sharing configuration between design and testbench via `include`:
COMPILE_ARGS 		+= -I$(SRC_DIR)

# Include the testbench sources:
VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL = tb

# List test modules to run, separated by commas and without the .py suffix:
COCOTB_TEST_MODULES = test

# include cocotb's make rules to take care of the simulator setup
include $(shell cocotb-config --makefiles)/Makefile.sim
