# Makefile
SIM ?= icarus
FST ?= -fst
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src
PROJECT_SOURCES = *.v

ifneq ($(GATES),yes)

# RTL simulation:
SIM_BUILD = sim_build/rtl
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))

else

# Gate level simulation:
SIM_BUILD = sim_build/gl
COMPILE_ARGS += -DGL_TEST
COMPILE_ARGS += -DFUNCTIONAL
COMPILE_ARGS += -DSIM
COMPILE_ARGS += -DNO_SPECIFY
COMPILE_ARGS += -gno-specify
COMPILE_ARGS += -gicarus-misc

PLUSARGS += +icarus:init-empty-queue

STDCELL_ORIG = $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog/sg13g2_stdcell.v
STDCELL_PATCHED = $(SIM_BUILD)/sg13g2_stdcell_patched.v

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

COMPILE_ARGS += -I$(SRC_DIR)
VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL = tb

MODULE = test

include $(shell cocotb-config --makefiles)/Makefile.sim
