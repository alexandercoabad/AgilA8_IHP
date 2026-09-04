![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# AgilA8 - an 8-bit Microcontroller
Agila is Tagalog for "eagle" - specifically evoking the Philippine Eagle (Haribon), the country's national bird. AgilA8 pairs that with A8, the name of the CPU core at the center of the design: Agil + A8 = AgilA8, the two overlapping on a shared capital A.

Tapeout of this project is sponsored by the IEEE Industrial Electronics & Photonics Philippine Joint Chapter (IEEE IES-IPS PH).

## Layout 

https://gds-viewer.tinytapeout.com/?model=https://alexandercoabad.github.io/AgilA8_IHP/tinytapeout.oas&pdk=ihp-sg13g2




3D Viewer: [https://gds-viewer.tinytapeout.com/?model=https://alexandercoabad.github.io/AgilA8_IHP/tinytapeout.oas&pdk=sky130A](https://gds-viewer.tinytapeout.com/?model=https://alexandercoabad.github.io/AgilA8_IHP/tinytapeout.oas&pdk=ihp-sg13g2)


## Block Diagram
<img width="712" height="883" alt="image" src="https://github.com/user-attachments/assets/d0df1d37-4bc0-4fc7-bd44-8b95111ab5ba" />


## How it works

AgilA8 is a compact 8-bit microcontroller built around A8, a custom
16-instruction CPU (see `docs/ISA.md`), with memory-mapped GPIO, a 16-bit
timer, and PWM generation.

### On-chip memory: boot ROM + shared RAM

The low 256 bytes of address space are on-chip, split across two
purpose-built blocks:

- **`boot_rom`** (IMEM 0x0000-0x007F, 128 bytes, fixed content) - always
  active, holds a small GPIO-based bootloader (see "Loading a program"
  below) plus its own timeout fallback to external flash.
- **`shared_ram`** (128 bytes, one physical array) - serves as DMEM
  0x00-0x7F from one port and IMEM 0x80-0xFF from another. The same
  128 bytes back both roles rather than two separate 128-byte arrays,
  since DMEM and IMEM accesses are never needed in the same cycle
  (same reasoning the shared QSPI engine below relies on) - this
  roughly halves the flip-flop cost of on-chip storage versus two
  independent arrays. See `shared_ram.v`'s header for the full
  reasoning, including why this specific pairing (a bootloaded
  program's own scratch data would alias its own instructions) is
  fine for this design's actual use case but wouldn't be for a
  general-purpose "arbitrary program plus separate scratch RAM" role.

This on-chip storage is the reason the project targets `info.yaml`'s
current **3x2** tile budget rather than the 1x2 the design started at.
That number came from actual GDS runs, not an area estimate - the same
design first tried 6x2 tiles (comfortable, but wasteful once
`shared_ram`'s merge cut on-chip flip-flop count by roughly 40%), then
4x2 at the default `PL_TARGET_DENSITY_PCT: 45`, which took multiple
hours of global placement *without converging* - OpenROAD's GPL kept
running because overflow never dropped below threshold, not because
placement itself is inherently slow. Raising it to `50` (in
`src/config.json`) let that 4x2 floorplan pass in about 30 minutes, at
roughly 50% utilization.
That headroom made 3x2 worth trying, and it needed `PL_TARGET_DENSITY_PCT: 70`
to place at all - but this time the run's own log tells a very
different story than the 4x2 attempts: global placement genuinely
*converged*, finishing at iteration 449 with overflow down to 0.0995,
in 2.52 seconds (`28-openroad-globalplacement/runtime.txt`, from the
`gds.yaml` CI run pushed as `bf17067`). The same log reports
`Minimum Feasible Density: 0.6800` for this floorplan - meaning 70 is
only 2 points above the actual placement floor, not an arbitrary
round number. Final routed utilization came out to 67.717%, matching
that ceiling closely. So unlike the 4x2/45 failure, this isn't a case
of placement struggling; it's a case of otherwise-clean placement
having very little room left to give if the design grows further.
For reference, in this same run the actual time sinks in the full GDS
flow are detailed routing (~11m38s) and Magic DRC (~4m51s) - global
placement is a rounding error against those by comparison.
Cell count alone doesn't predict any of this: flattened synthesis puts
this design at roughly 61% of the pre-merge design's cell count,
comparable raw cells-per-die-area, but a much higher *mux* share of
the design (largely the shared-engine and shared-RAM arbitration
logic) than a flip-flop-dominated netlist has - and that logic mix,
not just cell count, is what made the default density target too
tight for the 4x2 floorplan and what leaves 3x2 with only ~2 points of
density headroom at 70. If you change
`shared_ram.v`/`qspi_shared_engine.v` substantially or resize the tile
budget again, expect to revisit this value rather than assume 70 is
still appropriate - and check the global placement log's own
`Minimum Feasible Density` line first, since it directly tells you the
floor before you waste a run finding it by trial and error.

### Everything else: external QSPI flash/PSRAM

The rest of DMEM (0x80-0xEF, 0xF5-0xF6) lives on one of the Tiny
Tapeout QSPI Pmod's two PSRAM chips (RAM A / CS1), using standard
`02h`/`03h` Write/Read commands. External flash (CS0, standard `03h`
Read) backs anything IMEM needs beyond the on-chip 256 bytes, and is
also where `boot_rom`'s timeout path falls back to if no bootload is
requested (see below) - so flash is a fallback/extension, not a hard
requirement for basic operation, the way it was before `boot_rom` and
`shared_ram` existed. Only plain, single-line SPI commands are used -
deliberately not flash's continuous-read mode or PSRAM's QPI mode,
both of which need a mode-byte/setup sequence that's easy to get
subtly wrong without hardware to verify against.

### Loading a program without the Pmod

`boot_rom` implements a simple GPIO bit-banged protocol (`ui_in[0]`
DATA, `ui_in[1]` CLOCK, `ui_in[2]` START) for loading a program
directly into `shared_ram` at runtime, with no Pmod required - see
`test/build_boot_rom.py`'s docstring for the exact wire protocol. If no
START is seen within a bounded timeout, `boot_rom` sets a `FLASH_MODE`
flag (register below) and hands off to external flash instead, so an
unattended board still boots something useful.

This handoff went through two real, found-and-fixed bugs worth knowing
about if you're reading the address-routing logic in `tt_um_agila8.v`:
setting `FLASH_MODE` used to make `boot_rom` itself briefly
unreachable for its own remaining instructions (fixed by never gating
`boot_rom`'s own 0x00-0x7F range on the flag), and the flash address
rebase used to be discontinuous exactly at IMEM 0x0100 for any
flash-mode program longer than 128 bytes (fixed by using one
unconditional `-0x80` rebase instead of switching formulas at that
boundary). Both are covered by dedicated regression tests
(`test/tb_boundary.v`, `test/sim_full_top.py`) if you want the details
or are modifying this logic further.

**Leftover register state on the timeout path** - worth flagging on
its own, not a bug: the timeout loop leaves `r1=31` and `r6=31` (both
driven by its own timeout-counter/threshold comparison) and `r4=0`
(the last masked GPIO_IN read) sitting in the register file when
control hands off to flash, without resetting them. `r2`, `r3`, `r5`,
and `r7` happen to still be 0 on this specific path, but that's
incidental to the current loop structure, not a guarantee future
changes to `boot_rom` would preserve. Any flash program reached this
way needs to explicitly initialize whatever registers it actually
cares about rather than assume a clean start - `r1`/`r6` in particular
will not be 0.

### General-purpose SPI (CS2) - requires one board modification

A third front-end, a general-purpose SPI master intended for driving an
external device (an LCD, an ADC, another MCU), shares the same physical
lines using CS2. **This requires one board modification first**: on the
stock QSPI Pmod, CS2 ("RAM B") is wired directly to a second, populated
PSRAM chip, not out to any external connector pin. Per the Pmod's own
documentation ([mole99/qspi-pmod](https://github.com/mole99/qspi-pmod)),
each of its three chip-select traces can be cut on the back of the
board - doing so for CS2 disables that second PSRAM chip (a 1k pull-up
holds its `/CS` disabled) and makes the pad available via a through-hole
header pin as a plain input or output. That's a documented, intended
modification on the board as sold, not a custom respin - and it leaves
flash (CS0) and RAM A (CS1) untouched, so IMEM/DMEM are unaffected.
Until that trace is cut, this peripheral is functionally inert: CS2
still selects the live RAM B chip, so its transfers just talk to that
PSRAM with the wrong command protocol rather than reaching any external
device. See `qspi_shared_engine.v`'s header for the full explanation.

### Why one shared SPI engine

All three off-chip front-ends (flash, PSRAM, and the general-purpose SPI
controller) are driven by one shared SPI shift engine rather than three
separate FSMs, since they're never active at the same time (see below)
and consolidating saves real area - roughly 85 flip-flops for the
shared engine plus three thin front-ends, versus about 196 flip-flops
for three independent controllers.

Because `imem_valid` and `dmem_valid` are never asserted in the same
cycle (fetch and memory-access are separate, sequential states in the
core's FSM), and the DMEM-side peripherals are mutually exclusive by
address decode, the shared engine can grant flash/PSRAM/SPI with a
simple fixed-priority mux rather than needing real bus arbitration -
by construction, at most one of the three is ever requesting at once.

### Address map

| Address range | Device                                              |
| -------------- | --------------------------------------------------- |
| 0x00 - 0x7F    | RAM (on-chip `shared_ram`, DMEM port - see above)    |
| 0x80 - 0xEF, 0xF5 - 0xF6 | RAM (external PSRAM, RAM A)               |
| 0xF0 - 0xF2    | GPIO                                                 |
| 0xF3 - 0xF4    | SPI (general-purpose - requires a board mod, see above) |
| 0xF7           | FLASH_MODE (see "Loading a program" above)           |
| 0xF8 - 0xFB    | Timer                                                |
| 0xFC - 0xFD    | PWM                                                  |

> **Note:** `0xF3`/`0xF4`/`0xF7` used to be plain RAM in earlier
> revisions of this design; they now belong to the SPI controller and
> the FLASH_MODE flag respectively. Any old program that stored
> ordinary data at those three addresses will now silently hit a
> peripheral register instead of RAM.

Instructions are fetched from a separate 16-bit IMEM address space
(`boot_rom` 0x0000-0x007F, `shared_ram`'s IMEM port 0x0080-0x00FF once
a program is loaded, external flash beyond that or once `FLASH_MODE` is
set) - two consecutive bytes per instruction (big-endian: high byte at
PC, low byte at PC+1). IMEM isn't part of the 8-bit DMEM address space
in the table above.

### IO

| # | Input       | Output                           | Bidirectional                    |
| - | ----------- | -------------------------------- | --------------------------------- |
| 0 | GPIO in 0   | GPIO out 0                       | Flash CS (CS0)                    |
| 1 | GPIO in 1   | GPIO out 1                       | SD0 - MOSI (shared flash/PSRAM)   |
| 2 | GPIO in 2   | GPIO out 2                       | SD1 - MISO (shared flash/PSRAM)   |
| 3 | GPIO in 3   | GPIO out 3                       | SCK (shared flash/PSRAM)          |
| 4 | GPIO in 4   | GPIO out 4                       | SD2 (held high, unused)           |
| 5 | GPIO in 5   | GPIO out 5                       | SD3 (held high, unused)           |
| 6 | GPIO in 6   | GPIO out 6                       | RAM A CS (CS1)                    |
| 7 | GPIO in 7   | PWM output/Halted Status Output  | SPI CS (CS2, general-purpose SPI - requires cutting the RAM B trace first, see below) |


#### GPIO

| Register | Address     | Description                                                      |
| -------- | ----------- | ------------------------------------------------------------------ |
| GPIO_OUT | 0xF0 (R/W)  | Write sets `uo_out[6:0]`; read returns the last value written    |
| GPIO_IN  | 0xF1 (R)    | Reads the current state of `ui_in[7:0]`                          |
| GPIO_DIR | 0xF2 (R/W)  | Controls `uo_out[7]` multiplexing (Bit 7: `0` = PWM output [default], `1` = CPU `halted` status output) |

`uo_out[7]` defaults to the **PWM output** on reset (`GPIO_DIR[7] = 0`). Writing `1` to `GPIO_DIR[7]` re-routes `uo_out[7]` to output the CPU's **`halted`** status signal.

#### SPI (general-purpose) - requires a board modification first

This peripheral's register interface (`SPI_DATA`/`SPI_CTRL` below) is
correct SPI-master logic, but **it needs one physical modification to
the QSPI Pmod before it can reach anything external**. On the stock
board, CS2 ("RAM B") is wired directly to a second, populated PSRAM
chip - using this peripheral as-is just sends SPI traffic to that real
PSRAM using the wrong command set, and reaches no external device.

Per the Pmod's own documentation
([mole99/qspi-pmod](https://github.com/mole99/qspi-pmod)): each of the
three chip-select traces on the board can be cut, on the back of the
PCB, to disable that chip - a 1k pull-up then holds its `/CS` disabled,
and the pad becomes available via a through-hole header pin as a plain
input or output. Cutting **CS2's** trace specifically disables RAM B
and frees exactly the pin this peripheral needs - flash (CS0) and RAM A
(CS1) are untouched, so IMEM/DMEM keep working normally. This is a
documented, intended modification on the board as sold, not a custom
PCB respin.

Until that cut is made, treat this peripheral as inert. If you don't
want to modify the board (or just want the simplest path for something
like an e-paper display, which is slow enough that bit-banging is a
non-issue), drive the external device over the GPIO pins in software
instead - `uo_out[6:0]` and `ui_in[7:0]` are on a separate header from
the QSPI Pmod's `uio` bus entirely, so they aren't affected by any of
the above either way.

| Register | Address     | Description                                                        |
| -------- | ----------- | -------------------------------------------------------------------- |
| SPI_DATA | 0xF3 (R/W)  | Write: shifts the byte out (CS auto-asserted for the transfer, **blocking** until the 8-bit transfer physically completes). Read: returns the byte simultaneously shifted in from MISO during the most recent transfer, without starting a new one - to read a byte from a slave, write a dummy `0x00` and then read DATA back (standard full-duplex SPI) |
| SPI_CTRL | 0xF4 (R/W)  | Bits[1:0] = SCK clock divider: `00` = fastest (~sys_clk/2, matches flash/PSRAM speed), `01` = ~sys_clk/8, `10` = ~sys_clk/32, `11` = ~sys_clk/128 (**reset default** - start slow, let software speed up once the attached device's timing is known to tolerate it) |

Each `SPI_DATA` write is deliberately blocking rather than
fire-and-forget: the core has no instruction cache, so the very next
instruction fetch also needs this same shared bus. Blocking keeps this
peripheral's transfers inside the same single-active-transaction
invariant the shared engine already depends on for flash/PSRAM, with no
separate arbitration hardware needed. CS is likewise auto-pulsed per
byte (asserted only during the active transfer) rather than held low
across a logical multi-byte burst - genuinely continuous bursts aren't
possible on this hardware anyway, since unrelated flash-fetch traffic
would otherwise appear on the shared lines mid-burst; auto-pulsing at
least keeps CS deasserted while that happens, so the attached device
correctly ignores it.

#### FLASH_MODE

| Register    | Address     | Description                                                                |
| ----------- | ----------- | ----------------------------------------------------------------------------- |
| FLASH_MODE  | 0xF7 (W)    | Write-any-value-to-set, no readback. Once set, IMEM 0x0080 and up resolves to external flash instead of `shared_ram`/`boot_rom` - see "Loading a program" above. Set automatically by `boot_rom`'s own bootload timeout; not normally written by application code |

#### Timer

| Register    | Address     | Description                                                    |
| ----------- | ----------- | ---------------------------------------------------------------- |
| TIMER_LO    | 0xF8 (R)    | Bits 7:0 of the free-running 16-bit counter                    |
| TIMER_HI    | 0xF9 (R)    | Bits 15:8 of the counter                                       |
| TIMER_CTRL  | 0xFA (R/W)  | Bit 0 = enable (counts up once per clock while set). Writing bit 1 = 1 resets the counter to 0 |
| TIMER_FLAG  | 0xFB (R/W)  | Bit 0 = overflow (set when the counter wraps past 0xFFFF); any write clears it |

#### PWM

| Register  | Address     | Description                                                        |
| --------- | ----------- | ---------------------------------------------------------------------- |
| PWM_DUTY  | 0xFC (R/W)  | 8-bit duty cycle out of a free-running 256-cycle period. `0xFF` is a special-cased always-on |
| PWM_CTRL  | 0xFD (R/W)  | Bit 0 = enable. Output is forced low whenever disabled, regardless of PWM_DUTY |

## How to test

### The CI suite (`test/test.py`)

This is what actually runs on every push - it's what `make` (RTL mode)
and `GATES=yes make` (the `gl_test` CI job, against the real
synthesized netlist) both execute via `test/tb.v`. It's four cocotb
tests, and each one is written to make the *same* assertions
meaningful in both simulation modes: anything that reads internal
hierarchy (`dut.user_project.core...`, register file contents, `pc()`)
is wrapped in `if ... is not None:` and simply skipped in GL mode,
where that hierarchy doesn't exist in the synthesized netlist - only
externally-observable behavior (`uo_out`, whether the design halts at
all) is checked unconditionally in both modes.

1. **`test_bootloader`** - the primary end-to-end path: bit-bangs a
   program in over `ui_in[0:2]` (see "Loading a program" above) rather
   than pre-loading memory directly, so it's also exercising the
   bit-bang protocol itself, not just what runs afterward. The payload
   first sets `GPIO_DIR = 0xFF` at `0xF2` (needed so HALT status can
   reach `uo_out[7]` even in GL mode, where there's no internal
   `halted` signal to peek at directly), then runs `ADDI r1,r0,5`;
   `ADDI r2,r0,3`; `ADD r3,r1,r2`, writes `r3` out to `GPIO_DATA`
   (`0xF0`), and halts. RTL-only checks confirm `r1==5`, `r2==3`,
   `r3==8`; the check that also holds in GL mode confirms `uo_out` is
   fully resolvable (no `X`/`Z` - see the `imem_addr` reset bug this
   test is what originally caught) and its low nibble reads back `8`,
   the value that was written to `GPIO_DATA`.
2. **`test_boundary_continuity`** - regression test for a
   flash-address continuity bug in `tt_um_agila8.v` (a discontinuous
   rebase exactly at IMEM `0x0100` that silently re-executed a flash
   program's first 128 bytes for anything longer). Loads directly into
   the behavioral flash model (`fmem`, via `load_flash_image()`)
   instead of bit-banging, since the point here is exercising flash
   fetch across that specific address boundary, not the GPIO
   bootloader path test 1 already covers. The program sets `r6=1`,
   pads with 62 `NOP`s to straddle `0x0100`, then sets `r5=17` and
   halts. RTL-only checks confirm both `r5==17` and `r6==1` - `r6`
   matters because a reset-then-increment register nets to the same
   value whether a duplicate lap silently ran or not, so `r5` alone
   wouldn't reliably catch this bug even though it looks sufficient.
3. **`test_flash_regression`** - general-purpose flash + PSRAM
   regression. Runs `ADDI`, `OR`, and address arithmetic to compute
   `r3 = 15 OR 240 (as 8-bit) = 255`, writes it to external PSRAM at
   address 150, reads it back into `r5`, and halts. RTL-only checks
   confirm every intermediate register (`r1..r5`) alongside the
   round-tripped PSRAM value, so a failure here localizes to either
   the ALU op or the PSRAM write/read path rather than just "something
   is wrong."
4. **`test_full_opcode_regression`** - the broadest test: a
   pre-assembled 93-word machine-code image (every opcode in the ISA
   at least once) loaded directly into flash. Unlike the other three,
   this one never bit-bangs a boot payload in at all - it waits out
   `boot_rom`'s own timeout so the design falls through into
   `FLASH_MODE` on its own, then drives `ui_in = 0x55` to exercise
   general-purpose input handling too. RTL-only checks confirm all
   seven general-purpose registers (`r1..r7`) against known-good final
   values, which only line up if every opcode class executed
   correctly.

### Standalone debug testbenches (manual, not run in CI)

These predate the cocotb suite above and exist as independent,
lower-level cross-checks and debugging aids, not replacements for it -
`test/sim_full_top.py` and `test/test_boundary_continuity.py` (the
Python one, distinct from the cocotb test of the same name above)
exist as *independent* cross-checks of the address-routing logic
outside cocotb entirely.

1. **`test/tb_bootloader.v`** - a standalone version of the GPIO
   bootloader path, self-checking (`RESULT: PASS`/`FAIL`) without
   cocotb.
2. **`test/tb_boundary.v`** (run `test/build_boundary_test.py` first to
   generate its `imem.hex`) - the original, standalone version of the
   boundary-continuity regression, checking the final PC lands exactly
   where continuous addressing predicts.
3. **`test/tb_regression.v`** (run `test/build_flash_test.py` first) -
   the original standalone flash/PSRAM regression.
4. **`test/tb_debug6.v`** - a raw cycle-by-cycle trace tool (PC, key
   registers, `shared_ram` contents) for debugging changes to this
   logic; no pass/fail of its own.

Each Verilog testbench that reads an `imem.hex` needs it generated
first by its matching `build_*.py` script, and `vvp` needs to be run
from `test/` so `$readmemh` finds it - the two `tb_*.v` files that use
this file (`tb_boundary.v`, `tb_regression.v`) expect *different*
program content, so regenerate the right one before switching between
them.

Before committing to a tapeout, the QSPI Pmod flash-read timing margin
(`read_delay_cfg`, now handled centrally in `qspi_shared_engine.v`) is
worth validating on real hardware first, since interconnect delay isn't
visible in behavioral simulation - see the FPGA bring-up guide for the
Tiny Tapeout FPGA Development Kit + QSPI Pmod path used for that.

## External hardware

- [Tiny Tapeout QSPI Pmod](https://store.tinytapeout.com/products/QSPI-Pmod-p716541602),
  plugged into the demoboard's bidirectional Pmod header. The flash chip
  (program memory) and one of the two PSRAM chips (RAM A, data memory)
  are used as designed. The second PSRAM chip (RAM B / CS2) needs its
  chip-select trace cut on the back of the Pmod PCB (documented,
  intended modification - see
  [mole99/qspi-pmod](https://github.com/mole99/qspi-pmod)) before the
  general-purpose SPI peripheral can drive an external device through
  it; on an unmodified board that peripheral just talks to the
  still-populated RAM B chip instead of anything external.
- Without that modification, drive an external SPI device (e.g. an
  e-paper display) over the separate `ui_in`/`uo_out` GPIO header
  instead, bit-banging the protocol in software - that header is
  independent of the QSPI Pmod's `uio` bus and works either way.
- Tiny Tapeout demoboard, or the
  [FPGA Development Kit](https://store.tinytapeout.com/products/FPGA-Development-Kit-p813805747)
  for pre-tapeout bring-up on real silicon-adjacent hardware.


# Acknowledgments & Attribution

## Sponsorship

Tapeout of this project is sponsored by the IEEE Industrial Electronics
& Photonics Philippine Joint Chapter (IEEE IES-IPS PH).

This file documents the open-source tools, process design kit, and prior
art that AbadMCU depends on or was inspired by. It's split into two
categories that are easy to conflate but legally distinct:

1. **Tools and IP actually incorporated into this design** - their
   licenses (all Apache-2.0) place real obligations on redistribution.
2. **Architectural inspiration from prior projects** - no code was
   copied from these; crediting them is good academic/community
   practice, not a license requirement, since taking inspiration from
   a *design pattern* (as opposed to copying source text) isn't a
   Copyright event.

---

## 1. Tools & IP incorporated into this design (Apache-2.0)

The physical chip (GDS) produced from this repository directly embeds
standard-cell layouts from, and was built using, the following
Apache-2.0-licensed projects. Their copyright notices are reproduced
below per Apache-2.0 \u00a74; none of them ship a separate `NOTICE` file as
of this writing (checked: skywater-pdk's repository root contains only
`LICENSE` and `AUTHORS`, no `NOTICE` - worth re-checking the others
listed here yourself before a formal release, since this wasn't
exhaustively verified for every entry.

### SkyWater SKY130 PDK
The standard-cell library design was synthesized and hardened
against.

```
Copyright 2020 SkyWater PDK Authors
Licensed under the Apache License, Version 2.0 (the "License");
may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
```
Source: https://github.com/google/skywater-pdk

### open_pdks
PDK build/installer tooling used to assemble the sky130 PDK for the
hardening flow.

Source: https://github.com/fossi-foundation/open-pdks (Apache-2.0)

### OpenLane / OpenROAD
The RTL-to-GDS tool flow (synthesis, place & route, STA, DRC/LVS) that
produced this design's GDS.

```
OpenLane is \u00a92020-2024 Efabless Corporation and is available under
the Apache License, version 2.0.
```
Source: https://github.com/The-OpenROAD-Project/OpenLane

If citing academically:
> M. Shalan and T. Edwards, "Building OpenLANE: A 130nm OpenROAD-based
> Tapeout-Proven Flow," 2020 IEEE/ACM International Conference on
> Computer-Aided Design (ICCAD), San Diego, CA, USA, 2020, pp. 1-6.

### Tiny Tapeout project templates / tt-support-tools
The `tt_um_*` port convention, `info.yaml` schema, and CI/build
scaffolding this repo's structure follows.

Source: https://github.com/TinyTapeout (templates are Apache-2.0 by
default per Tiny Tapeout's own FAQ)

---

## 2. Architectural inspiration (no code reused)

AgilA8's central design decision - CPU with no on-chip memory,
program fetched from external QSPI flash, working data in external
QSPI PSRAM, sharing physical SPI wires between them via a separate chip
selects - follows the same strategic pattern pioneered on Tiny Tapeout
by the following projects. **No RTL, ISA encoding, or source code from
either project was copied** - AgilA8's CPU core, instruction set, and
peripheral RTL were independently designed and implemented. What's
credited here is the *architectural pattern*, not any specific
implementation of it.

### TinyQV (Michael Bell)
First (and to date, most complete) demonstration of this
flash+PSRAM-over-shared-QSPI-Pmod pattern on Tiny Tapeout, including
the specific convention of a single active chip-select and
code-execution-restricted-to-flash.

Source: https://github.com/MichaelBell/tinyQV (Apache-2.0)

### KianV (Hirosh Dabui / splinedrive)
Independent, earlier demonstration of the same external-memory-over-QSPI
pattern (both the uLinux and bare-metal editions), predating this
project.

Source: https://github.com/splinedrive/kianRiscV,
https://github.com/TinyTapeout/KianV-RV32IMA-RISC-V-uLinux-SoC
(check the repository's own LICENSE file directly before citing a
specific license - it wasn't confirmed via an explicit license badge
at the time this was written)

### RISC-V (conceptual influence only)
A8's `r0`-hardwired-to-zero convention and load/store architectural
style are modeled on RISC-V's design philosophy. RISC-V is an open,
freely usable ISA specification; no code is reused here, so this
carries no license obligation. **TT8 is not RISC-V-compliant** - it's
a custom 16-bit-instruction, 8-bit-datapath ISA in the RISC-V style,
and should not be described as a RISC-V implementation or use the
RISC-V trademark/logo.

---

## 3. What's original to this project

- The A8 instruction encoding (16-bit fixed-width, R-type/I-type
  split, the specific opcode table) is a custom design, not derived
  from any existing ISA's bit layout.
- All RTL in this repository (`a8_core.v`, `a8_alu.v`,
  `a8_regfile.v`, `a8_peripherals.v`, `qspi_shared_engine.v`,
  `tt_um_agila8.v`) was independently written for this project.
  `qspi_shared_engine.v` consolidates what were previously three
  separate controllers (`qspi_flash_reader.v` for flash,
  `qspi_psram_ctrl.v` for PSRAM, and a standalone `spi_ctrl.v` for the
  general-purpose SPI peripheral) into one shared engine - see that
  file's header for why, and for the general-purpose SPI register
  semantics (now merged in rather than a separate file).
- The verification suite, bug fixes, and STA signoff analysis
  documented in this repository's history are this project's own work.

---

## Unverified claims to double-check before formal publication

- A code comment (originally in `qspi_flash_reader.v`, which may or may
  not still be present in the repo as reference material - it isn't
  part of the module actually instantiated after the merge) attributes
  a ~20ns round-trip timing margin figure to "TinyQV's own QSPI
  controller comments." This has not been independently confirmed
  against TinyQV's actual source - verify both the exact figure/its
  origin, and which file it currently lives in, before citing it as a
  TinyQV-derived fact.
- The Apache-2.0 NOTICE-file check above was only performed for
  skywater-pdk; confirm the other three Apache-2.0 entries (open_pdks,
  OpenLane, Tiny Tapeout templates) don't ship their own NOTICE files
  before finalizing this document, since if any of them do, its
  contents would need to be reproduced here per \u00a74(d).

