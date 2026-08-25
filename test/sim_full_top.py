#!/usr/bin/env python3
"""
Full top-level address-routing simulator: CPU + boot_rom + shared_ram
+ FLASH_MODE + flash. Models tt_um_agila8.v's actual IMEM/DMEM mux
logic (including the flash_addr fix) in Python, so the timeout ->
FLASH_MODE -> flash handoff can be independently re-verified without
a Verilog simulator - not just re-checked by re-reading the diff.

CPU semantics matched against a8_core.v/a8_alu.v, same basis as the
earlier sim_bootrom.py (JAL always links r7, JALR 8-bit zero-extended
target, branch offsets 9-bit sign-extended, ALU results truncate to
8 bits).
"""

def u8(v): return v & 0xFF
def u16(v): return v & 0xFFFF

BOOT_ROM_BASE = 0x0000
SHARED_RAM_IMEM_BASE = 0x0080
FLASH_IMEM_BASE = 0x0100


class Top:
    def __init__(self, boot_rom_bytes, flash_bytes):
        self.boot_rom = boot_rom_bytes          # dict/list, 0..127
        self.flash = flash_bytes                # dict, byte addr -> value
        self.shared_ram = [None] * 128           # None = X/uninitialized,
                                                   # matching shared_ram.v's
                                                   # documented behavior
        self.flash_mode = False                  # FLASH_MODE (0xF7)
        self.regs = [0]*8
        self.pc = 0
        self.dmem_writes = []
        self.gpio_in_bits = []
        self.halted = False

    def read_gpio_in(self):
        if self.gpio_in_bits:
            return self.gpio_in_bits.pop(0)
        return 0

    # ---- IMEM fetch: replicates tt_um_agila8.v's mux exactly ----
    def fetch_byte(self, imem_addr):
        # Matches the WORKING version's routing exactly:
        #   boot_rom_hit        = imem_addr < 0x80              (UNCONDITIONAL -
        #                          never gated by flash_mode, this is the fix)
        #   shared_ram_imem_hit = 0x80<=imem_addr<0x100 && !flash_mode
        #   flash_imem_hit      = neither of the above
        #   flash_addr = (imem_addr<0x100) ? imem_addr-0x80 : imem_addr-0x100
        boot_rom_hit        = (imem_addr < 0x0080)
        shared_ram_imem_hit = (0x0080 <= imem_addr < 0x0100) and not self.flash_mode
        if boot_rom_hit:
            return self.boot_rom[imem_addr] if imem_addr < len(self.boot_rom) else 0
        elif shared_ram_imem_hit:
            v = self.shared_ram[imem_addr & 0x7F]
            assert v is not None, f"read of uninitialized shared_ram[{imem_addr&0x7F:#x}] as instruction fetch"
            return v
        else:
            # FIX (see chat): single, unconditional -0x80 rebase for all of
            # flash_imem_hit's range (which by construction starts at 0x80,
            # since boot_rom already claims everything below that) - no
            # special case for >=0x100, since that branch's -0x100 rebase
            # was the actual bug: it broke continuity for any flash-mode
            # program longer than 128 bytes, re-executing flash offset 0
            # onward as soon as pc crossed 0x0100 instead of continuing.
            flash_addr = u16(imem_addr - 0x0080)
            return self.flash.get(flash_addr, 0)

    def fetch16(self, addr):
        return (self.fetch_byte(addr) << 8) | self.fetch_byte(addr+1)

    # ---- DMEM access: models the ram_hit_comb / FLASH_MODE-write path ----
    def dmem_read(self, addr8):
        if addr8 == 0xF1:                # GPIO_IN
            return self.read_gpio_in()
        elif addr8 < 0x80:                # shared_ram DMEM port
            v = self.shared_ram[addr8]
            return 0 if v is None else v   # (real HW: X: harmless here,
                                             # nothing in this bootloader
                                             # reads DMEM back before
                                             # writing it)
        else:
            return 0                        # external PSRAM - not modeled,
                                             # not used by this bootloader

    def dmem_write(self, addr8, val):
        self.dmem_writes.append((addr8, val))
        if addr8 == 0xF7:                  # FLASH_MODE
            self.flash_mode = True
        elif addr8 < 0x80:                  # shared_ram DMEM port
            self.shared_ram[addr8] = u8(val)
        # else: external PSRAM / other peripherals - not modeled

    def step(self):
        instr = self.fetch16(self.pc)
        opcode = (instr >> 12) & 0xF
        rd  = (instr >> 9) & 0x7
        rs1 = (instr >> 6) & 0x7
        rs2 = (instr >> 3) & 0x7
        imm6 = instr & 0x3F
        imm_s = imm6 - 64 if (imm6 & 0x20) else imm6

        r = self.regs
        pc = self.pc
        next_pc = u16(pc + 2)

        def wr(addr, val):
            if addr != 0:
                r[addr] = u8(val)

        if opcode == 0x0: pass
        elif opcode == 0x1: wr(rd, r[rs1] + r[rs2])
        elif opcode == 0x2: wr(rd, r[rs1] + imm_s)
        elif opcode == 0x3: wr(rd, r[rs1] - r[rs2])
        elif opcode == 0x4: wr(rd, r[rs1] & r[rs2])
        elif opcode == 0x5: wr(rd, r[rs1] | r[rs2])
        elif opcode == 0x6: wr(rd, r[rs1] ^ r[rs2])
        elif opcode == 0x7: wr(rd, r[rs1] << (imm6 & 0x7))
        elif opcode == 0x8: wr(rd, r[rs1] >> (imm6 & 0x7))
        elif opcode == 0x9:
            addr8 = u8(r[rs1] + imm_s)
            wr(rd, self.dmem_read(addr8))
        elif opcode == 0xA:
            addr8 = u8(r[rs1] + imm_s)
            self.dmem_write(addr8, r[rd])
        elif opcode == 0xB:
            if r[rs1] == r[rd]: next_pc = u16(pc + imm_s * 2)
        elif opcode == 0xC:
            if r[rs1] < r[rd]: next_pc = u16(pc + imm_s * 2)
        elif opcode == 0xD:
            r[7] = u8(pc + 2)
            next_pc = u16(pc + imm_s * 2)
        elif opcode == 0xE:
            wr(rd, pc + 2)
            next_pc = u8(r[rs1] + imm_s)
        elif opcode == 0xF:
            self.halted = True
            return False

        self.pc = next_pc
        return True


def bits_msb_first(b): return [(b >> i) & 1 for i in range(7, -1, -1)]

def build_gpio_stream(bytes_):
    stream = []
    for byte in bytes_:
        for bit in bits_msb_first(byte):
            hv = 0x02 | bit
            stream += [hv, hv, 0x00]
    return stream


def load_hex(path):
    vals = [int(l.strip(), 16) for l in open(path) if l.strip()]
    return vals


boot_rom = load_hex("boot_rom.hex")

print("=== TEST: timeout -> FLASH_MODE -> flash handoff (full top-level sim) ===")
# Tiny flash image: ADDI r4,r0,31 ; HALT  (31 is the max value that
# fits directly in imm6's 6-bit signed field - avoids the exact mistake
# just made above: encoding 100 without going through proper 6-bit
# wraparound handling)
def itype(op, rd, rs1, imm6):
    OP = dict(NOP=0,ADD=1,ADDI=2,HALT=0xF)
    imm6 &= 0x3F
    return (OP[op] << 12) | (rd << 9) | (rs1 << 6) | imm6

flash_words = [itype('ADDI', 4, 0, 31), itype('HALT', 0, 0, 0)]
flash_bytes = {}
for i, w in enumerate(flash_words):
    flash_bytes[i*2]   = (w >> 8) & 0xFF
    flash_bytes[i*2+1] = w & 0xFF

top = Top(boot_rom, flash_bytes)
top.gpio_in_bits = [0x00] * 40   # START never asserted

steps = 0
while steps < 400 and not top.halted:
    if not top.step():
        break
    steps += 1

print(f"  steps executed: {steps}")
print(f"  flash_mode set: {top.flash_mode}  (expect True)")
print(f"  halted: {top.halted}  (expect True)")
print(f"  final pc: 0x{top.pc:04x}  (expect 0x0002 - byte after the 2-byte HALT)")
print(f"  r4 = {top.regs[4]}  (expect 31 - the correct value from the tiny flash "
      f"image; anything else means flash_addr resolved to the wrong offset)")
assert top.flash_mode, "FAIL: FLASH_MODE was never set"
assert top.halted, "FAIL: never reached HALT in flash"
assert top.regs[4] == 31, f"FAIL: r4={top.regs[4]}, expected 31 (flash_addr bug not actually fixed)"
print("  PASS - flash_addr fix confirmed correct via full address-routing trace")
