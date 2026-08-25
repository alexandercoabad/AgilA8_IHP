#!/usr/bin/env python3
"""
Self-checking firmware assembler for gate-level-safe testing.

Why this exists: gate-level netlists don't preserve RTL hierarchy or
internal signal names - `dut.user_project.core.regfile.regs[1]` and
similar simply don't exist post-synthesis (confirmed via real CI
failure: AttributeError, "user_project contains no object named
core"). The only thing guaranteed to survive identically in both RTL
and gate-level simulation is the top-level port interface. So instead
of computing results and reading them back via internal probes, each
firmware program built with this module VERIFIES ITS OWN RESULTS in
hardware (via BEQ, the same self-checking pattern used earlier in this
project) and reports pass/fail by writing a fixed sentinel byte to
GPIO_OUT (0xF0) - observable via uo_out[6:0] from any simulation level.

On any check failure, the firmware writes a FAIL sentinel and halts
immediately, INLINE at the point of failure rather than jumping to a
shared handler - deliberately avoiding BEQ/JAL's +-62-byte range limit
entirely instead of having to reason about it per check.
"""

OP = dict(NOP=0, ADD=1, ADDI=2, SUB=3, AND=4, OR=5, XOR=6, SLL=7, SRL=8,
          LW=9, SW=0xA, BEQ=0xB, BLT=0xC, JAL=0xD, JALR=0xE, HALT=0xF)

PASS_SENTINEL = 0x7F  # 0b01111111 - all of uo_out[6:0], easy to spot
FAIL_SENTINEL = 0x55  # 0b01010101 - visually distinct from PASS


def itype(op, rd, rs1, imm6):
    return (OP[op] << 12) | (rd << 9) | (rs1 << 6) | (imm6 & 0x3F)


def rtype(op, rd, rs1, rs2):
    return (OP[op] << 12) | (rd << 9) | (rs1 << 6) | (rs2 << 3)


def load_byte_chunks(value):
    """Return signed 6-bit chunks (each -32..31) summing to `value` mod
    256 via chained addition - ported verbatim from scratch_helpers.py
    (verified there via a full 0-255 sweep, not just a spot check)."""
    value &= 0xFF

    def ok(chunks):
        acc = 0
        for c in chunks:
            acc = (acc + c) & 0xFF
        return acc == value

    for c1 in range(-32, 32):
        if ok([c1]):
            return [c1]
    for c1 in range(-32, 32):
        for c2 in range(-32, 32):
            if ok([c1, c2]):
                return [c1, c2]
    for c1 in range(-32, 32):
        for c2 in range(-32, 32):
            for c3 in range(-32, 32):
                if ok([c1, c2, c3]):
                    return [c1, c2, c3]
    reach2 = {}
    for c1 in range(-32, 32):
        for c2 in range(-32, 32):
            v = (c1 + c2) & 0xFF
            if v not in reach2:
                reach2[v] = (c1, c2)
    for v1, (c1, c2) in reach2.items():
        v2 = (value - v1) & 0xFF
        if v2 in reach2:
            c3, c4 = reach2[v2]
            return [c1, c2, c3, c4]
    reach4 = {}
    for v1, (c1, c2) in reach2.items():
        for v2, (c3, c4) in reach2.items():
            v = (v1 + v2) & 0xFF
            if v not in reach4:
                reach4[v] = (c1, c2, c3, c4)
    for v4, chunks4 in reach4.items():
        c5 = (value - v4) & 0xFF
        if c5 > 127:
            c5 -= 256
        if -32 <= c5 <= 31:
            return list(chunks4) + [c5]
    raise AssertionError(f"value {value} needs >5 chunks")


class Asm:
    def __init__(self):
        self.instrs = []
        self.labels = {}
        self.fixups = []

    def addr(self):
        return len(self.instrs) * 2

    def label(self, name):
        self.labels[name] = self.addr()

    def emit(self, word):
        self.instrs.append(word & 0xFFFF)
        return self.addr() - 2

    def ADDI(self, rd, rs1, imm): self.emit(itype('ADDI', rd, rs1, imm))
    def ADD(self, rd, rs1, rs2):  self.emit(rtype('ADD', rd, rs1, rs2))
    def SUB(self, rd, rs1, rs2):  self.emit(rtype('SUB', rd, rs1, rs2))
    def AND(self, rd, rs1, rs2):  self.emit(rtype('AND', rd, rs1, rs2))
    def OR(self, rd, rs1, rs2):   self.emit(rtype('OR', rd, rs1, rs2))
    def XOR(self, rd, rs1, rs2):  self.emit(rtype('XOR', rd, rs1, rs2))
    def SLL(self, rd, rs1, imm):  self.emit(itype('SLL', rd, rs1, imm))
    def SRL(self, rd, rs1, imm):  self.emit(itype('SRL', rd, rs1, imm))
    def LW(self, rd, rs1, imm):   self.emit(itype('LW', rd, rs1, imm))
    def SW(self, rsrc, rs1, imm): self.emit(itype('SW', rsrc, rs1, imm))
    def NOP(self):                self.emit(itype('NOP', 0, 0, 0))
    def HALT(self):                self.emit(itype('HALT', 0, 0, 0))

    def BEQ(self, rs1, rs2_as_rd, target_label):
        idx = self.emit(itype('BEQ', rs2_as_rd, rs1, 0))
        self.fixups.append((idx, target_label))

    def BLT(self, rs1, rs2_as_rd, target_label):
        idx = self.emit(itype('BLT', rs2_as_rd, rs1, 0))
        self.fixups.append((idx, target_label))

    def JAL(self, rd, target_label):
        idx = self.emit(itype('JAL', rd, 0, 0))
        self.fixups.append((idx, target_label))

    def JALR(self, rd, rs1, imm): self.emit(itype('JALR', rd, rs1, imm))

    def load_byte(self, rd, value):
        """Load an arbitrary byte value into rd via chained ADDI."""
        chunks = load_byte_chunks(value)
        self.ADDI(rd, 0, chunks[0])
        for c in chunks[1:]:
            self.ADDI(rd, rd, c)

    def gpio_write(self, rd, value):
        """Write `value` to GPIO_OUT (0xF0), building it into rd first."""
        self.load_byte(rd, value)
        self.SW(rd, 0, -16)  # -16 sign-extends to 0xF0

    def check_eq(self, actual_reg, expected_value, scratch_reg, fail_reg):
        """Self-checking assert: if actual_reg != expected_value, write
        FAIL_SENTINEL to GPIO_OUT and halt immediately, right here -
        deliberately not a jump to a shared handler, to sidestep
        BEQ/JAL's +-62-byte range limit entirely rather than having to
        reason about it per check site."""
        self.load_byte(scratch_reg, expected_value)
        skip = f"__ok_{len(self.fixups)}_{id(self)}"
        self.BEQ(actual_reg, scratch_reg, skip)
        self.gpio_write(fail_reg, FAIL_SENTINEL)
        self.HALT()
        self.label(skip)

    def finalize(self):
        words = list(self.instrs)
        for idx, target in self.fixups:
            target_addr = self.labels[target]
            off = (target_addr - idx) // 2
            assert -32 <= off <= 31, (
                f"branch/jump offset {off} out of range "
                f"(from 0x{idx:02x} to {target}=0x{target_addr:02x})")
            opcode_rd_rs1 = words[idx // 2] & 0xFFC0
            words[idx // 2] = opcode_rd_rs1 | (off & 0x3F)
        return words

    def to_bytes(self):
        out = bytearray()
        for w in self.finalize():
            out.append((w >> 8) & 0xFF)
            out.append(w & 0xFF)
        return bytes(out)


if __name__ == '__main__':
    # quick self-check: a program that checks 2+2==4 (pass) should reach
    # HALT with GPIO_OUT=PASS_SENTINEL; verify no exceptions during
    # assembly/finalize at minimum (real pass/fail needs simulation,
    # covered separately).
    a = Asm()
    a.ADDI(1, 0, 2)
    a.ADDI(2, 0, 2)
    a.ADD(3, 1, 2)
    a.check_eq(3, 4, 6, 7)
    a.gpio_write(1, PASS_SENTINEL)
    a.HALT()
    words = a.finalize()
    print(f"Self-check program assembled OK: {len(words)} words, "
          f"{len(words)*2} bytes")
