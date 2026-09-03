`default_nettype none
`timescale 1ns / 1fs

module tb;

    reg [7:0] ui_in;
    reg [7:0] uio_in;
    wire [7:0] uo_out;
    wire [7:0] uio_out;
    wire [7:0] uio_oe;
    reg clk;
    reg rst_n;
    reg ena;

    initial begin
        clk = 0;
        rst_n = 0;
        ena = 0;
        ui_in = 8'h00;
        uio_in = 8'h00;
    end

    // uio[7:0] = {CS2, CS1, SD3, SD2, SCK, SD1, SD0, CS0} - matches
    // tb_regression.v's proven mapping/behavioral SPI models for the
    // flash and PSRAM devices, ported here (same instance name,
    // "user_project", that the rest of this testbench and the GATES
    // netlist swap both already use) so test.py's consolidated
    // bootloader/boundary/flash/full-opcode suite can run against a
    // single tb.v in both RTL and GL modes. uio_in[2] (MISO) can't be
    // driven by both cocotb (a plain `reg` deposit on the whole byte)
    // and this behavioral model's continuous output, so it's spliced
    // in at the instantiation port instead of assigned into the reg.
    wire flash_cs_n = uio_out[0];
    wire spi_mosi   = uio_out[1];
    wire spi_sck    = uio_out[3];
    wire psram_cs_n = uio_out[6];
    reg  miso;
    wire [7:0] uio_in_actual = {uio_in[7:3], miso, uio_in[1:0]};

    // ---- Flash behavioral model (03h read) ----
    // Sized/poked by test.py's poke_fmem()/load_flash_image() per test
    // rather than $readmemh'd from a fixture file - there is no
    // checked-in imem.hex, and each test wants different contents.
    reg [7:0] fmem [0:511];
    integer fi;
    initial for (fi = 0; fi < 512; fi = fi + 1) fmem[fi] = 8'h00;
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

    tt_um_agila8 user_project (
        .ui_in   (ui_in),
        .uo_out  (uo_out),
        .uio_in  (uio_in_actual),
        .uio_out (uio_out),
        .uio_oe  (uio_oe),
        .ena     (ena),
        .clk     (clk),
        .rst_n   (rst_n)
    );

    initial begin
        $dumpfile("tb.vcd");
        $dumpvars(0, tb);
    end

endmodule

