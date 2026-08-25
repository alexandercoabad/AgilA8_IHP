#!/usr/bin/env python3
OP = dict(NOP=0,ADD=1,ADDI=2,SUB=3,AND=4,OR=5,XOR=6,SLL=7,SRL=8,
          LW=9,SW=0xA,BEQ=0xB,BLT=0xC,JAL=0xD,JALR=0xE,HALT=0xF)

def itype(op, rd, rs1, imm6):
    return (OP[op] << 12) | (rd << 9) | (rs1 << 6) | (imm6 & 0x3F)

def rtype(op, rd, rs1, rs2):
    return (OP[op] << 12) | (rd << 9) | (rs1 << 6) | (rs2 << 3)

prog = []
prog.append(itype('ADDI', 1, 0, 15))      # r1 = 15
prog.append(itype('ADDI', 2, 0, -16))     # r2 = 0xF0 (240, via sign-extended -16)
prog.append(rtype('OR',  3, 1, 2))         # r3 = 15 | 240 = 255
prog.append(itype('ADDI', 4, 0, 31))       # r4 = 31
prog.append(itype('ADDI', 4, 4, 31))       # r4 = 62
prog.append(itype('ADDI', 4, 4, 31))       # r4 = 93
prog.append(itype('ADDI', 4, 4, 31))       # r4 = 124
prog.append(itype('ADDI', 4, 4, 26))       # r4 = 150 (0x96, genuinely
                                             # within PSRAM's 0x80-0xEF -
                                             # 100 (0x64) is BELOW 0x80,
                                             # my own earlier mistake)
prog.append(itype('SW', 3, 4, 0))          # PSRAM[100] = 255
prog.append(itype('LW', 5, 4, 0))          # r5 = PSRAM[100] (readback, expect 255)
prog.append(itype('HALT', 0, 0, 0))

mem = bytearray(512)
for i, w in enumerate(prog):
    mem[i*2]   = (w >> 8) & 0xFF
    mem[i*2+1] = w & 0xFF

with open('imem.hex', 'w') as f:
    for b in mem:
        f.write(f"{b:02x}\n")

print(f"Program is {len(prog)*2} bytes.")
print("Expected: r1=15 r2=240 r3=255 r4=150 r5=255, pmem[150]=255, halted")
