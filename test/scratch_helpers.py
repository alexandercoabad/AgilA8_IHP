#!/usr/bin/env python3
"""Scratch module to compute and validate instruction sequences before
transcribing into test.py. Not part of the delivered test suite."""

OP = dict(NOP=0, ADD=1, ADDI=2, SUB=3, AND=4, OR=5, XOR=6, SLL=7, SRL=8,
          LW=9, SW=0xA, BEQ=0xB, BLT=0xC, JAL=0xD, JALR=0xE, HALT=0xF)


def itype(op, rd, rs1, imm6):
    return (OP[op] << 12) | (rd << 9) | (rs1 << 6) | (imm6 & 0x3F)


def rtype(op, rd, rs1, rs2):
    return (OP[op] << 12) | (rd << 9) | (rs1 << 6) | (rs2 << 3)


def load_byte_chunks(value):
    """Return a list of signed 6-bit chunks (each -32..31) that sum to
    `value` mod 256 via chained addition, shortest first - same
    brute-force approach used earlier in this project (chained addition
    of N bounded chunks has real, non-obvious coverage gaps, so this
    searches rather than uses a hand-derived heuristic)."""
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

    # *** BUG FIX (verified via a full 0-255 sweep, not just the original
    # 15-value spot check - see chat): the 4-chunk meet-in-the-middle
    # above has a real, narrow gap. Two chunks in [-32,31] only reach
    # sums in {0..62} u {192..255} mod 256 - {63..191} is a genuine dead
    # zone for any single 2-chunk pair. Combining two such reaches still
    # can't bridge 125/126/127 specifically: same-side pairs cap out at
    # 124 (62+62) or floor at 128 (192+192), and cross-side pairs cover
    # 192..255 wrapping to 0..61 - none of the three combinations ever
    # lands on 125, 126, or 127. A 5th chunk trivially closes this: take
    # any reachable 4-chunk value 62 or fewer away from the target
    # (guaranteed to exist, since {0..62} alone already spans a 63-wide
    # window) and cover the remaining gap with one more chunk.
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


def emit_load_byte(words, rd, value):
    """Append instructions loading `value` into register rd."""
    chunks = load_byte_chunks(value)
    words.append(itype('ADDI', rd, 0, chunks[0]))
    for c in chunks[1:]:
        words.append(itype('ADDI', rd, rd, c))


def emit_psram_write(words, rsrc, addr, addr_scratch_reg):
    """Append instructions writing register rsrc's value to PSRAM[addr].
    Builds the address into addr_scratch_reg first (PSRAM addresses
    0x80-0xEF aren't reachable via a single r0-relative SW - only
    0-31/224-255 are)."""
    emit_load_byte(words, addr_scratch_reg, addr)
    words.append(itype('SW', rsrc, addr_scratch_reg, 0))


def emit_gpio_done(words, scratch_reg, value=0x7F):
    """Append instructions writing `value` to GPIO_OUT (0xF0) as a
    completion sentinel. 0xF0 = sext(-16), reachable directly via
    r0-relative addressing (imm6=-16 is in range), no scratch register
    needed for the address - but we still need a register holding the
    VALUE to write (GPIO_OUT is written via SW's rd/source field)."""
    emit_load_byte(words, scratch_reg, value)
    words.append(itype('SW', scratch_reg, 0, -16))


if __name__ == '__main__':
    # quick self-check
    for v in [0, 1, 31, 32, 63, 100, 127, 128, 150, 200, 255, 240, 17, 130, 2]:
        chunks = load_byte_chunks(v)
        acc = 0
        for c in chunks:
            acc = (acc + c) & 0xFF
        assert acc == v, f"FAIL for {v}: got {acc} via {chunks}"
    print("load_byte_chunks self-check OK")
