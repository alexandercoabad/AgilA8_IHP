`default_nettype none
`timescale 1ns/1ps

module tb_debug_full;
    reg clk = 0;
    reg rst_n = 0;
    always #(1000.0/64.0/2.0) clk = ~clk;

    reg  [7:0] ui_in  = 8'h00;
    wire [7:0] uo_out;
    reg  [7:0] uio_in = 8'h00;
    wire [7:0] uio_out;
    wire [7:0] uio_oe;

    tt_um_agila8 dut (
        .ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in),
        .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(1'b1), .clk(clk), .rst_n(rst_n)
    );

    wire flash_cs_n = uio_out[0];
    wire spi_mosi   = uio_out[1];
    wire spi_sck    = uio_out[3];
    wire psram_cs_n = uio_out[6];
    reg  miso;
    always @(*) uio_in[2] = miso;

    reg [7:0] fmem [0:511];
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

    integer i;
    reg [15:0] words [0:99];
    initial begin
        words[0]=16'h2205; words[1]=16'h240a; words[2]=16'h1650; words[3]=16'h3888;
        words[4]=16'h4a50; words[5]=16'h5a50; words[6]=16'h6a50; words[7]=16'h7c42;
        words[8]=16'h8d82; words[9]=16'h223d; words[10]=16'h3208; words[11]=16'h240a;
        words[12]=16'ha410; words[13]=16'h9e10; words[14]=16'h221f; words[15]=16'h225f;
        words[16]=16'h225f; words[17]=16'h2247; words[18]=16'h241b; words[19]=16'ha440;
        words[20]=16'h9640; words[21]=16'h2205; words[22]=16'hb242; words[23]=16'hf000;
        words[24]=16'h281f; words[25]=16'h290b; words[26]=16'h2900; words[27]=16'h2900;
        words[28]=16'h2a03; words[29]=16'h2c01; words[30]=16'h2400; words[31]=16'h3b70;
        words[32]=16'h2481; words[33]=16'hb142; words[34]=16'hb03d; words[35]=16'h2203;
        words[36]=16'hc205; words[37]=16'h261f; words[38]=16'h26df; words[39]=16'h26df;
        words[40]=16'h26d2; words[41]=16'h261f; words[42]=16'h26df; words[43]=16'h26cf;
        words[44]=16'h26c0; words[45]=16'hd005; words[46]=16'h281f; words[47]=16'h291f;
        words[48]=16'h291f; words[49]=16'h2912; words[50]=16'h281f; words[51]=16'h291f;
        words[52]=16'h291a; words[53]=16'h2900; words[54]=16'h2220; words[55]=16'h2260;
        words[56]=16'h2260; words[57]=16'h2262; words[58]=16'he476; words[59]=16'hf000;
        words[60]=16'h2a1f; words[61]=16'h2b5f; words[62]=16'h2b44; words[63]=16'h2b40;
        words[64]=16'h2430; words[65]=16'h2480; words[66]=16'h2480; words[67]=16'h2480;
        words[68]=16'h2220; words[69]=16'h2260; words[70]=16'h226a; words[71]=16'h2240;
        words[72]=16'ha280; words[73]=16'h9680; words[74]=16'h9881; words[75]=16'h243c;
        words[76]=16'h2480; words[77]=16'h2480; words[78]=16'h2480; words[79]=16'h221f;
        words[80]=16'h225f; words[81]=16'h2242; words[82]=16'h2240; words[83]=16'ha280;
        words[84]=16'h9c80; words[85]=16'h2201; words[86]=16'h2240; words[87]=16'h2240;
        words[88]=16'h2240; words[89]=16'ha2be; words[90]=16'h9ebe; words[91]=16'hf000;

        for (i = 0; i < 92; i = i + 1) begin
            fmem[i*2]   = words[i][15:8];
            fmem[i*2+1] = words[i][7:0];
        end
    end

    integer cycle_count = 0;
    always @(posedge clk) cycle_count = cycle_count + 1;

    reg [15:0] last_pc = 16'hFFFF;
    always @(posedge clk) begin
        if (rst_n && dut.user_project.core.pc !== last_pc && dut.user_project.core.state == 3'd3) begin
            // print whenever we ENTER EXECUTE with a new pc value
            $display("t=%0t cyc=%0d pc=0x%04x instr=0x%04x opcode=%0d flash_mode=%b r1=%0d r2=%0d r3=%0d r4=%0d r5=%0d r6=%0d r7=%0d",
                $time, cycle_count, dut.user_project.core.pc, dut.user_project.core.instr,
                dut.user_project.core.opcode, dut.user_project.flash_mode_r,
                dut.user_project.core.regfile.regs[1], dut.user_project.core.regfile.regs[2],
                dut.user_project.core.regfile.regs[3], dut.user_project.core.regfile.regs[4],
                dut.user_project.core.regfile.regs[5], dut.user_project.core.regfile.regs[6],
                dut.user_project.core.regfile.regs[7]);
            last_pc = dut.user_project.core.pc;
        end
    end

    initial begin
        rst_n = 0;
        ui_in = 0;
        repeat (5) @(posedge clk);
        rst_n = 1;

        // wait for flash_mode_r like the cocotb test does
        while (dut.user_project.flash_mode_r !== 1'b1 && cycle_count < 10000) @(posedge clk);
        $display("=== flash_mode_r=%b at cycle %0d ===", dut.user_project.flash_mode_r, cycle_count);
        ui_in = 8'h55;

        repeat (30000) @(posedge clk);
        $display("=== FINAL: pc=0x%04x halted=%b cycle=%0d ===", dut.user_project.core.pc, dut.user_project.halted, cycle_count);
        $finish;
    end

endmodule
