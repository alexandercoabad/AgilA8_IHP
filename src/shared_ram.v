`default_nettype none

// Shared on-chip RAM: 128 bytes total, serving BOTH DMEM (0x00-0x7F,
// data access via LW/SW) and IMEM/IRAM (0x80-0xFF from the CPU's PC
// perspective - the caller strips the fixed 0x80 offset via bit-
// slicing before it reaches this module, so imem_addr here is already
// 0x00-0x7F) from the SAME physical byte array. This is the same
// "never accessed same-cycle" trick already used for sharing the QSPI
// engine across flash/PSRAM/SPI: a8_core never asserts imem_valid and
// dmem_valid in the same cycle, and the caller additionally gates each
// port's valid so DMEM only ever sees addresses <0x80 and IMEM only
// ever sees the 0x80-0xFF range (sliced to 0x00-0x7F) - see
// tt_um_agila8.v's shared_ram_inst wiring for the exact gating this
// module relies on. Only one physical read/write port is needed
// internally as a result, which is what makes this half the area of
// two separate 128-byte macros.
//
// CAVEAT: mem[] is NOT initialized on reset - it is genuinely
// undefined (X in simulation; some fixed but unspecified state on real
// silicon) until something writes to it. This is expected, not a bug:
// the whole point of DMEM 0x00-0x7F is that the bootloader writes a
// program there before anything reads it back as instructions. Don't
// add a simulation-only initial block here - it would hide the real
// hardware behavior rather than model it, and every testbench that
// exercises this module should write before it reads, matching how a
// real bootload always has to happen first.

module shared_ram (
    input  wire        clk,
    input  wire        rst_n,

    // DMEM port - 0x00-0x7F as seen from the CPU's data-memory address
    // space. The caller gates dmem_valid so this is never asserted for
    // an address outside that range; only the low 7 bits are ever
    // meaningful, but the full 8-bit dmem_addr is accepted for
    // convenience at the call site.
    input  wire [7:0]  dmem_addr,
    input  wire [7:0]  dmem_wdata,
    input  wire        dmem_we,
    input  wire        dmem_valid,
    output reg  [7:0]  dmem_rdata,
    output reg         dmem_ready,

    // IMEM port - already offset-stripped by the caller to 0x00-0x7F.
    // Read-only: instruction fetch never writes.
    input  wire [6:0]  imem_addr,
    input  wire        imem_valid,
    output reg  [7:0]  imem_rdata,
    output reg         imem_ready
);

    reg [7:0] mem [0:127];

    // *** Fix (see chat): merge both callers' addresses into ONE index
    // before it reaches the array, instead of leaving mem[dmem_index]
    // and mem[imem_addr] as two independent expressions. The two are
    // never architecturally active in the same cycle (see module
    // header), but that's an invariant about caller behavior - nothing
    // in two separate address expressions tells the SYNTHESIS TOOL
    // that, so it inferred genuine two-read-port memory (measured via
    // yosys: 5948 cells for this module vs 3615/3707 for the old
    // ram32.v/iram.v it replaced - about 60% MORE cells per byte than
    // either single-port predecessor, not less, and structurally the
    // kind of dual-port shape that's much harder to place and route,
    // not just bigger). A single merged index makes the single-port
    // structure explicit instead of hoping the tool infers it.
    wire       access_valid = dmem_valid || imem_valid;
    wire       access_we    = dmem_valid && dmem_we;  // imem never writes
    wire [6:0] access_addr  = imem_valid ? imem_addr : dmem_addr[6:0];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            dmem_ready <= 1'b0;
            imem_ready <= 1'b0;
        end else begin
            dmem_ready <= 1'b0;
            imem_ready <= 1'b0;

            if (access_valid) begin
                if (access_we) begin
                    mem[access_addr] <= dmem_wdata;
                end else if (imem_valid) begin
                    imem_rdata <= mem[access_addr];
                end else begin
                    dmem_rdata <= mem[access_addr];
                end
                dmem_ready <= dmem_valid;
                imem_ready <= imem_valid;
            end
        end
    end

endmodule
