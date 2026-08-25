`default_nettype none
`timescale 1ns/1ps

// Boundary-continuity regression: same timeout -> FLASH_MODE -> flash
// handoff as tb_regression.v, but with a flash program specifically
// crossing the imem 0x0100 boundary (flash offset 0x80), to catch the
// flash_addr discontinuity bug the two-branch (-0x80 / -0x100) formula
// had: it jumped flash_addr from 127 back down to 0 exactly at
// imem_addr=0x100, silently re-executing flash's own offset-0 code
// instead of continuing to offset 128. r6 increments exactly once at
// flash offset 0-3, then 62 NOPs pad out to offset 0x80 where a marker
// (r5=17) sits - if the boundary wraps, r6 fires a second time before
// r5 is ever reached, and r5 stays 0 forever (program re-loops instead
// of reaching HALT, or reaches a stale FLASH_MODE'd re-entry - either
// way, easy to tell apart from a genuine PASS).

module tb_boundary;

    reg clk = 0;
    reg rst_n = 0;
    always #(1000.0/64.0/2.0) clk = ~clk;  // 64MHz - update if clock_hz changes

    reg  [7:0] ui_in = 8'h00;
    wire [7:0] uo_out;
    reg  [7:0] uio_in = 8'h00;
    wire [7:0] uio_out, uio_oe;

    tt_um_agila8 dut (
        .ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in),
        .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(1'b1), .clk(clk), .rst_n(rst_n)
    );

    // uio[7:0] = {CS2, CS1, SD3, SD2, SCK, SD1, SD0, CS0}
    wire flash_cs_n = uio_out[0];
    wire spi_mosi   = uio_out[1];
    wire spi_sck    = uio_out[3];
    wire psram_cs_n = uio_out[6];
    reg  miso;
    always @(*) uio_in[2] = miso;

    // ---- Flash behavioral model (03h read) ----
    reg [7:0] fmem [0:511];
    initial $readmemh("imem.hex", fmem);
    reg [30:0] f_sh; reg [5:0] f_cnt; reg [7:0] f_data; reg f_miso;
    always @(posedge spi_sck or posedge flash_cs_n) begin
        if (flash_cs_n) f_cnt <= 0;
        else begin
            if (f_cnt < 32) f_sh <= {f_sh[29:0], spi_mosi};
            if (f_cnt == 31) f_data <= fmem[{f_sh[7:0], spi_mosi}];
            f_cnt <= f_cnt + 1;
        end
    end
    always @(negedge spi_sck or posedge flash_cs_n) begin
        if (flash_cs_n) f_miso <= 0;
        else if (f_cnt >= 32) begin
            case (f_cnt - 32)
                0: f_miso<=f_data[7]; 1: f_miso<=f_data[6]; 2: f_miso<=f_data[5]; 3: f_miso<=f_data[4];
                4: f_miso<=f_data[3]; 5: f_miso<=f_data[2]; 6: f_miso<=f_data[1]; 7: f_miso<=f_data[0];
                default: f_miso <= 0;
            endcase
        end
    end

    // ---- PSRAM behavioral model (02h write / 03h read) ----
    reg [7:0] pmem [0:255];
    integer pi; initial for (pi = 0; pi < 256; pi = pi + 1) pmem[pi] = 8'h00;
    reg [5:0] p_cnt; reg [7:0] p_op; reg [23:0] p_addr; reg [7:0] p_wd; reg p_miso;
    always @(posedge spi_sck or posedge psram_cs_n) begin
        if (psram_cs_n) p_cnt <= 0;
        else begin
            if (p_cnt < 8) p_op <= {p_op[6:0], spi_mosi};
            else if (p_cnt < 32) p_addr <= {p_addr[22:0], spi_mosi};
            else begin
                p_wd <= {p_wd[6:0], spi_mosi};
                if (p_cnt == 39 && p_op == 8'h02) pmem[p_addr[7:0]] <= {p_wd[6:0], spi_mosi};
            end
            p_cnt <= p_cnt + 1;
        end
    end
    always @(negedge spi_sck or posedge psram_cs_n) begin
        if (psram_cs_n) p_miso <= 0;
        else if (p_cnt >= 32 && p_op == 8'h03) begin
            case (p_cnt - 32)
                0: p_miso<=pmem[p_addr[7:0]][7]; 1: p_miso<=pmem[p_addr[7:0]][6];
                2: p_miso<=pmem[p_addr[7:0]][5]; 3: p_miso<=pmem[p_addr[7:0]][4];
                4: p_miso<=pmem[p_addr[7:0]][3]; 5: p_miso<=pmem[p_addr[7:0]][2];
                6: p_miso<=pmem[p_addr[7:0]][1]; 7: p_miso<=pmem[p_addr[7:0]][0];
                default: p_miso <= 0;
            endcase
        end
    end

    always @(*) begin
        if (!flash_cs_n) miso = f_miso;
        else if (!psram_cs_n) miso = p_miso;
        else miso = 1'b0;
    end

    integer cyc = 0;
    always @(posedge clk) cyc = cyc + 1;

    initial begin
        rst_n = 0;
        repeat (5) @(posedge clk);
        rst_n = 1;
        // Deliberately don't assert START on ui_in[2] - let boot_rom's
        // own timeout fire and fall through to flash, exercising that
        // path for the first time.

        fork
            begin
                wait (dut.halted == 1);
                $display("HALTED at cycle %0d", cyc);
            end
            begin
                repeat (400000) @(posedge clk);
                $display("TIMEOUT: never halted (cycle=%0d, pc=0x%04x, state=%0d)",
                          cyc, dut.core.pc, dut.core.state);
            end
        join_any
        disable fork;

        $display("=== FINAL STATE ===");
        $display("halted=%0d pc=0x%04x (expect 0x0102 - byte after the 2-byte HALT",
                  dut.halted, dut.core.pc);
        $display("      immediately following the marker at imem 0x0100; 0x0182 means");
        $display("      the boundary wrapped and the whole 128-byte image phantom-");
        $display("      restarted once before reaching HALT - r5/r6 alone can't tell");
        $display("      this apart, since a reset-then-reincrement of r6 during the");
        $display("      phantom pass nets to the same final value either way)");
        $display("r5=%0d (expect 17 - marker at flash offset 0x80)",
                  dut.core.regfile.regs[5]);
        $display("r6=%0d (expect 1)", dut.core.regfile.regs[6]);
        if (dut.halted && dut.core.pc == 16'h0102
            && dut.core.regfile.regs[5] == 17 && dut.core.regfile.regs[6] == 1)
            $display("RESULT: PASS - flash_addr is genuinely continuous across the 0x0100 boundary");
        else
            $display("RESULT: FAIL");
        $finish;
    end

endmodule
