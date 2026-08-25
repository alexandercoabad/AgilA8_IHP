# AgilA8 ISA

A8's instruction set: 16-bit fixed-width instructions, 8 general-purpose
registers (`r0`-`r7`, `r0` hardwired to zero), 8-bit data words, three
instruction formats.

## Instruction formats

**R-type** (`ADD`, `SUB`, `AND`, `OR`, `XOR`)

```
 15        12 11        9 8         6 5         3 2         0
+------------+-----------+-----------+-----------+-----------+
|   opcode   |    rd     |    rs1    |    rs2    |  unused   |
|   [15:12]  |   [11:9]  |   [8:6]   |   [5:3]   |   [2:0]   |
+------------+-----------+-----------+-----------+-----------+
```

**I-type** (`ADDI`, `SLL`, `SRL`, `LW`, `SW`, `BEQ`, `BLT`, `JALR`)

```
 15        12 11        9 8         6 5                     0
+------------+-----------+-----------+-----------------------+
|   opcode   |    rd     |    rs1    |     imm6 (signed)      |
|   [15:12]  |   [11:9]  |   [8:6]   |          [5:0]         |
+------------+-----------+-----------+-----------------------+
```

**JAL** (opcode + 6-bit signed word offset only)

```
 15        12 11                   6 5                     0
+------------+-----------------------+-----------------------+
|   opcode   | unused (rd, rs1 bits  |     imm6 (signed)      |
|   [15:12]  |   ignored)  [11:6]    |          [5:0]         |
+------------+-----------------------+-----------------------+
```

## Opcode table

| Opcode | Mnemonic | Type            | Semantics |
|--------|----------|-----------------|-----------|
| 0x0    | NOP      | -               | No-op |
| 0x1    | ADD      | R               | `rd = rs1 + rs2` |
| 0x2    | ADDI     | I               | `rd = rs1 + sext(imm6)` |
| 0x3    | SUB      | R               | `rd = rs1 - rs2` |
| 0x4    | AND      | R               | `rd = rs1 & rs2` |
| 0x5    | OR       | R               | `rd = rs1 \| rs2` |
| 0x6    | XOR      | R               | `rd = rs1 ^ rs2` |
| 0x7    | SLL      | I               | `rd = rs1 << imm6[2:0]` |
| 0x8    | SRL      | I               | `rd = rs1 >> imm6[2:0]` |
| 0x9    | LW       | I               | `rd = DMEM[rs1 + sext(imm6)]` |
| 0xA    | SW       | I               | `DMEM[rs1 + sext(imm6)] = rd` (rd holds the *source* register here, not a destination) |
| 0xB    | BEQ      | I               | `if (rs1 == rd) pc += sext(imm6)*2` (rd is the *second compare register*, not a destination) |
| 0xC    | BLT      | I               | `if (rs1 < rd) pc += sext(imm6)*2` (unsigned compare; same rd reuse as BEQ) |
| 0xD    | JAL      | word-offset only | `r7 = pc+2; pc += sext(imm6)*2` |
| 0xE    | JALR     | I               | `rd = pc+2; pc = {8'h00, rs1 + sext(imm6)}` |
| 0xF    | HALT     | -               | Stops the core |

## Quirks worth knowing before you write assembly

**JAL always writes the return address to r7.** The `rd` field in a JAL
instruction is encoded but silently ignored by hardware. This exact
assumption mismatch caused a real bug earlier in this project (a
subroutine that assumed it could choose its own link register).

**JALR's target is always zero-extended to 8 bits** — `{8'h00, rs1 +
sext(imm6)}` — so it can only ever land in `0x0000`-`0x00FF`, never
beyond, regardless of what's in the source register. This is *why* the
whole `FLASH_MODE` indirection scheme exists.

**BEQ/BLT's rd field is a second source register, not a destination.**
Both compare `rs1` against whatever's in the register the `rd` field
happens to name.
