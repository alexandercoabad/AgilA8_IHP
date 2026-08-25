#!/usr/bin/env python3
"""
Builds the four self-checking firmware programs used by test.py, using
asm_selfcheck.Asm. Kept separate from test.py so each program can be
assembled and sanity-checked standalone (`python3 build_selfcheck_programs.py`)
before ever touching cocotb.
"""

from asm_selfcheck import Asm, PASS_SENTINEL, FAIL_SENTINEL


# ---------------------------------------------------------------------
# Program 1: bootloader payload. Bit-banged in via GPIO at runtime (see
# test.py's send_byte_gpio), NOT preloaded into flash. Self-checks its
# own ADD result instead of relying on a register readback from Python.
# ---------------------------------------------------------------------

def build_bootloader_payload():
    a = Asm()
    a.load_byte(1, 5)
    a.load_byte(2, 3)
    a.ADD(3, 1, 2)                        # r3 = 5 + 3 = 8
    a.check_eq(3, 8, scratch_reg=6, fail_reg=7)
    a.gpio_write(7, PASS_SENTINEL)
    a.HALT()
    return a.to_bytes()


# ---------------------------------------------------------------------
# Program 2: boundary continuity. Same shape as the original raw-hex
# version (zero a counter, increment it exactly once, pad to EXACTLY
# flash offset 0x80 so the check code starts right where flash_addr's
# rebasing crosses the IMEM 0x0100 boundary), but self-checking.
#
# IMPORTANT: check_eq(r6==1) alone can't distinguish "ran once" from "a
# discontinuous flash_addr rebase silently re-executed this whole
# 128-byte block" - a reset-then-increment nets to r6=1 either way (see
# chat). The discriminator has to be TIMING: test.py polls uo_out for a
# BOUNDED window sized comfortably above the known-correct cycle count
# but below what a phantom relaunch would need - see test.py's
# BOUNDARY_TEST_CYCLE_BUDGET.
# ---------------------------------------------------------------------

def build_boundary_test():
    a = Asm()
    a.ADDI(6, 0, 0)                        # flash offset 0: r6 = 0
    a.ADDI(6, 6, 1)                        # flash offset 2: r6 += 1

    bytes_so_far = a.addr()                # 4
    pad_bytes_needed = 0x80 - bytes_so_far
    assert pad_bytes_needed % 2 == 0
    for _ in range(pad_bytes_needed // 2):
        a.NOP()
    assert a.addr() == 0x80, f"padding landed at 0x{a.addr():02x}, expected 0x80"

    a.check_eq(6, 1, scratch_reg=2, fail_reg=1)
    a.gpio_write(1, PASS_SENTINEL)
    a.HALT()
    return a.to_bytes()


# ---------------------------------------------------------------------
# Program 3: general ALU + PSRAM read/write regression.
# ---------------------------------------------------------------------

def build_flash_regression():
    a = Asm()
    a.load_byte(1, 15)
    a.load_byte(2, 240)
    a.OR(3, 1, 2)                          # r3 = 15 | 240 = 255
    a.check_eq(3, 255, scratch_reg=6, fail_reg=7)

    a.load_byte(4, 150)                    # PSRAM address (0x80-0xEF
                                             # window - not r0-relative
                                             # reachable, needs a real
                                             # register)
    a.SW(3, 4, 0)                          # PSRAM[150] = r3 (255)
    a.LW(5, 4, 0)                          # r5 = PSRAM[150] (readback)
    a.check_eq(5, 255, scratch_reg=6, fail_reg=7)

    a.gpio_write(7, PASS_SENTINEL)
    a.HALT()
    return a.to_bytes()


# ---------------------------------------------------------------------
# Program 4: full opcode regression. Rebuilt from scratch with proper
# labeled branches (the original raw-hex version looped forever - its
# JALR recomputed the exact same r1 value every pass through a fixed
# ADDI chain, so it always jumped back to the same target; see chat).
# Covers every opcode, a forward branch (taken), a backward branch
# (taken, bounded loop with an explicit exit check so it can't repeat
# the same mistake), JAL+JALR, memory read/write, and GPIO_IN.
# ---------------------------------------------------------------------

def build_full_opcode_regression():
    a = Asm()

    # ---- ALU ops ----
    a.load_byte(1, 100)
    a.load_byte(2, 37)
    a.ADD(3, 1, 2)                         # r3 = 137 mod 256 = 137
    a.check_eq(3, 137, scratch_reg=6, fail_reg=7)

    a.SUB(3, 1, 2)                         # r3 = 100 - 37 = 63
    a.check_eq(3, 63, scratch_reg=6, fail_reg=7)

    a.AND(3, 1, 2)                         # 100=0x64, 37=0x25 -> 0x24=36
    a.check_eq(3, 36, scratch_reg=6, fail_reg=7)

    a.OR(3, 1, 2)                          # 0x64|0x25=0x65=101
    a.check_eq(3, 101, scratch_reg=6, fail_reg=7)

    a.XOR(3, 1, 2)                         # 0x64^0x25=0x41=65
    a.check_eq(3, 65, scratch_reg=6, fail_reg=7)

    a.SLL(3, 2, 3)                         # 37<<3 = 296 mod 256 = 40
    a.check_eq(3, 40, scratch_reg=6, fail_reg=7)

    a.SRL(3, 1, 2)                         # 100>>2 = 25
    a.check_eq(3, 25, scratch_reg=6, fail_reg=7)

    # ---- Memory read/write (shared_ram DMEM range, address < 0x80) ----
    a.load_byte(4, 50)                     # address
    a.load_byte(5, 200)                    # value
    a.SW(5, 4, 0)                          # mem[50] = 200
    a.LW(3, 4, 0)                          # r3 = mem[50]
    a.check_eq(3, 200, scratch_reg=6, fail_reg=7)

    # ---- BEQ: forward branch, taken ----
    a.load_byte(1, 9)
    a.load_byte(2, 9)
    a.BEQ(1, 2, "beq_taken_ok")
    a.gpio_write(7, FAIL_SENTINEL)         # should have branched past this
    a.HALT()
    a.label("beq_taken_ok")

    # ---- BEQ: not taken (falls through) ----
    a.load_byte(1, 9)
    a.load_byte(2, 8)
    a.BEQ(1, 2, "beq_not_taken_bug")
    a.JAL(6, "beq_not_taken_ok")
    a.label("beq_not_taken_bug")
    a.gpio_write(7, FAIL_SENTINEL)
    a.HALT()
    a.label("beq_not_taken_ok")

    # ---- BLT: bounded backward-branch loop (counts 0 -> 5, with an
    #      explicit exit check so a broken comparison can't loop
    #      forever - unlike the original raw-hex version) ----
    a.load_byte(1, 0)                      # loop counter
    a.load_byte(2, 5)                      # loop limit
    a.label("count_loop")
    a.ADDI(1, 1, 1)
    a.BLT(1, 2, "count_loop")              # loop while r1 < 5
    a.check_eq(1, 5, scratch_reg=6, fail_reg=7)

    # ---- JAL + JALR: standard call/return idiom (matches RECV_BYTE's
    #      own convention elsewhere in this project - JAL always writes
    #      its link to r7 regardless of the encoded rd field, confirmed
    #      in a8_core.v: `rf_rd_addr <= 3'd7; // link register is
    #      always r7` - so this deliberately calls via JAL(7,...) and
    #      returns via JALR(0,7,0), not a made-up "jump forward past
    #      code" pattern that would have needed a pre-known target
    #      address instead of relying on that hardwired behavior) ----
    a.JAL(7, "subroutine")
    a.check_eq(1, 42, scratch_reg=2, fail_reg=6)  # r1=42 proves the
                                                    # subroutine ran and
                                                    # JALR returned here
    a.JAL(0, "after_subroutine")
    a.label("subroutine")
    a.load_byte(1, 42)
    a.JALR(0, 7, 0)                        # return to caller via r7
    a.label("after_subroutine")

    # ---- GPIO_IN readback ----
    a.LW(1, 0, -15)                         # r1 = GPIO_IN (0xF1)
    a.check_eq(1, 0x55, scratch_reg=6, fail_reg=7)

    a.gpio_write(7, PASS_SENTINEL)
    a.HALT()
    return a.to_bytes()


if __name__ == '__main__':
    for name, builder in [
        ('bootloader_payload', build_bootloader_payload),
        ('boundary_test', build_boundary_test),
        ('flash_regression', build_flash_regression),
        ('full_opcode_regression', build_full_opcode_regression),
    ]:
        b = builder()
        print(f"{name}: {len(b)} bytes")
