#!/usr/bin/env python3
"""
Workaround for a known Icarus Verilog / IHP sg13g2 PDK interaction:

IHP's sg13g2_stdcell.v routes each sequential cell's real CLK/D/RESET_B
(etc.) through internal `delayed_*` wires that are only driven via the
"delayed output" arguments of $setuphold/$recrem/$width timing-check
system tasks inside each cell's `specify` block. Icarus Verilog does not
implement that mechanism ("Timing checks are not supported and delayed
signal ... will not be driven"), so those wires float permanently and
every flip-flop/latch in a design built from this library reads X
forever in Icarus GL simulation - independent of the design on top of it.

This script inserts a direct pass-through `assign delayed_X = X;` right
after each `wire ... delayed_X ...;` declaration, restoring correct
functional behavior. This is safe for FUNCTIONAL-only simulation (no
timing checks are being verified anyway) but should NOT be used for a
timing-accurate / SDF-annotated run.

Usage:
    python3 patch_ihp_delayed_signals.py sg13g2_stdcell.v > sg13g2_stdcell.functional.v

Then compile GL tests against the patched file instead of the original,
e.g. in the iverilog command line that currently references
.../sg13g2_stdcell/verilog/sg13g2_stdcell.v.
"""

import re
import sys


def patch(content: str) -> str:
    lines = content.split("\n")
    out = []
    inserted = 0
    for line in lines:
        out.append(line)
        m = re.match(r"^\s*wire\s+(.*delayed_\w+.*);\s*$", line)
        if m:
            names = [n.strip() for n in m.group(1).split(",")]
            for n in names:
                if n.startswith("delayed_"):
                    real = n[len("delayed_"):]
                    out.append(f"\tassign {n} = {real};")
                    inserted += 1
    print(f"// patched: inserted {inserted} pass-through assigns for "
          f"delayed_* signals", file=sys.stderr)
    return "\n".join(out)


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <sg13g2_stdcell.v>", file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1]) as f:
        content = f.read()
    sys.stdout.write(patch(content))


if __name__ == "__main__":
    main()
