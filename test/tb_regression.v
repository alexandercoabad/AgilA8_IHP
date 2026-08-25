`default_nettype none
`timescale 1ns/1ps

// Full-chip regression: boot_rom is left to time out (no bootload
// request asserted), falls through to FLASH_MODE + JALR 0x0080 exactly
// as build_boot_rom.py's timeout path does (see tt_um_agila8.v's
// flash_addr comment for why 0x0080, not 0x0000 - that was an earlier,
// buggy version of this same design), then runs the established
// all-opcode golden-model test program from external flash - the same
// program used throughout this whole project's earlier verification
// rounds, now exercising the new shared_ram DMEM window (0x00-0x7F),
// external PSRAM (0x80-0xEF), and peripherals together under the new
// address map. (This comment was stale until now - the JALR target
// changed but this file's header didn't get updated at the time; the
// flash behavioral model below does a plain, unbiased fmem[addr]
// lookup with no offset assumptions of its own, so the test's actual
// pass/fail behavior was never affected by this - only the comment
// was wrong.)

module tb_regression;

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
        $display("halted=%0d pc=0x%04x", dut.halted, dut.core.pc);
        $display("r1=%0d r2=%0d r3=%0d r4=%0d r5=%0d r6=%0d r7=%0d",
                  dut.core.regfile.regs[1], dut.core.regfile.regs[2],
                  dut.core.regfile.regs[3], dut.core.regfile.regs[4],
                  dut.core.regfile.regs[5], dut.core.regfile.regs[6],
                  dut.core.regfile.regs[7]);
        $display("pmem[150] (external PSRAM)=%0d", pmem[150]);
        $display("uo_out=0x%02x", uo_out);
        $finish;
    end

endmodule
