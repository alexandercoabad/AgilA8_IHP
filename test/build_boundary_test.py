#!/usr/bin/env python3
OP = dict(NOP=0,ADD=1,ADDI=2,SUB=3,AND=4,OR=5,XOR=6,SLL=7,SRL=8,
          LW=9,SW=0xA,BEQ=0xB,BLT=0xC,JAL=0xD,JALR=0xE,HALT=0xF)

def itype(op, rd, rs1, imm6):
    imm6 &= 0x3F
    return (OP[op] << 12) | (rd << 9) | (rs1 << 6) | imm6

words  = [itype('ADDI', 6, 0, 0)]               # flash offset 0-1: r6 = 0
words += [itype('ADDI', 6, 6, 1)]               # flash offset 2-3: r6 += 1
                                                  # (should fire EXACTLY ONCE
                                                  # if rebasing is continuous)
words += [itype('NOP', 0, 0, 0)] * 62            # pad to flash offset 0x80
words += [itype('ADDI', 5, 0, 17)]               # flash offset 0x80-0x81: marker
words += [itype('HALT', 0, 0, 0)]

mem = bytearray(512)
for i, w in enumerate(words):
    mem[i*2]   = (w >> 8) & 0xFF
    mem[i*2+1] = w & 0xFF

with open('imem.hex', 'w') as f:
    for b in mem:
        f.write(f"{b:02x}\n")

print(f"Program is {len(words)*2} bytes.")
print("Expected: r5=17 (marker at flash offset 0x80), r6=1 (not 2 - counter must fire exactly once)")
