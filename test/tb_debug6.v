`default_nettype none
`timescale 1ns/1ps

module tb_debug6;
    reg clk = 0;
    always #10 clk = ~clk;
    reg rst_n = 0;

    reg  [7:0] ui_in = 8'h00;
    wire [7:0] uo_out;
    reg  [7:0] uio_in = 8'h00;
    wire [7:0] uio_out;
    wire [7:0] uio_oe;

    tt_um_agila8 dut (
        .ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in),
        .uio_out(uio_out), .uio_oe(uio_oe),
        .ena(1'b1), .clk(clk), .rst_n(rst_n)
    );

    localparam HOLD = 150;

    task set_bits(input data, input clock, input start);
        begin
            ui_in[0] = data;
            ui_in[1] = clock;
            ui_in[2] = start;
        end
    endtask

    task send_bit(input b);
        begin
            set_bits(b, 1'b0, 1'b1);
            repeat (HOLD) @(posedge clk);
            set_bits(b, 1'b1, 1'b1);
            repeat (HOLD) @(posedge clk);
            set_bits(b, 1'b0, 1'b1);
            repeat (HOLD) @(posedge clk);
        end
    endtask

    task send_byte(input [7:0] b);
        integer i;
        begin
            for (i = 7; i >= 0; i = i - 1)
                send_bit(b[i]);
        end
    endtask

    reg [7:0] prog [0:7];
    initial begin
        prog[0] = 8'h22; prog[1] = 8'h05;
        prog[2] = 8'h24; prog[3] = 8'h03;
        prog[4] = 8'h16; prog[5] = 8'h50;
        prog[6] = 8'hF0; prog[7] = 8'h00;
    end

    integer cyc = 0;
    reg [15:0] last_pc = 16'hFFFF;
    reg last_we = 0;
    always @(posedge clk) begin
        cyc = cyc + 1;
        if (dut.core.pc !== last_pc) begin
            $display("cyc=%0d pc=0x%04x state=%0d r1=%0d r2=%0d r3=%0d r5=%0d r7=%0d dmem_addr=0x%02x dmem_we=%b dmem_valid=%b dmem_wdata=0x%02x ram_hit=%b",
                cyc, dut.core.pc, dut.core.state,
                dut.core.regfile.regs[1], dut.core.regfile.regs[2], dut.core.regfile.regs[3],
                dut.core.regfile.regs[5], dut.core.regfile.regs[7],
                dut.dmem_addr, dut.dmem_we, dut.dmem_valid, dut.dmem_wdata, dut.ram_hit_comb);
            last_pc = dut.core.pc;
        end
        // Continuous per-cycle trace around any dmem_we activity,
        // regardless of whether pc also changed this cycle - dmem_valid
        // is a single-cycle pulse that may not land on the same cycle
        // as a pc transition.
        if (dut.dmem_we !== last_we) begin
            $display("  [we edge] cyc=%0d dmem_we: %b->%b  addr=0x%02x valid=%b wdata=0x%02x state=%0d shared_ram.dmem_valid=%b shared_ram.dmem_we=%b",
                cyc, last_we, dut.dmem_we, dut.dmem_addr, dut.dmem_valid, dut.dmem_wdata,
                dut.core.state, dut.shared_ram_inst.dmem_valid, dut.shared_ram_inst.dmem_we);
            last_we = dut.dmem_we;
        end
        if (cyc >= 7295 && cyc <= 7305) begin
            $display("  [full] cyc=%0d pc=0x%04x state=%0d dmem_valid=%b dmem_ready=%b dmem_we=%b dmem_addr=0x%02x shared_ram.ready=%b",
                cyc, dut.core.pc, dut.core.state, dut.dmem_valid, dut.dmem_ready,
                dut.dmem_we, dut.dmem_addr, dut.shared_ram_inst.dmem_ready);
        end
        if (cyc >= 32570 && cyc <= 32900) begin
            $display("  [imem80] cyc=%0d pc=0x%04x state=%0d imem_addr=0x%04x imem_valid=%b imem_ready=%b imem_rdata=0x%02x onchip=%b boot_rom_hit=%b shared_ram.imem_valid=%b shared_ram.imem_addr=0x%02x shared_ram.imem_rdata=0x%02x mem0=0x%02x mem1=0x%02x",
                cyc, dut.core.pc, dut.core.state, dut.imem_addr, dut.imem_valid, dut.imem_ready, dut.imem_rdata,
                dut.onchip_imem_hit, dut.boot_rom_hit,
                dut.shared_ram_inst.imem_valid, dut.shared_ram_inst.imem_addr, dut.shared_ram_inst.imem_rdata,
                dut.shared_ram_inst.mem[0], dut.shared_ram_inst.mem[1]);
        end
        if (cyc > 33000) begin
            $display("STOP at cyc=%0d pc=0x%04x state=%0d", cyc, dut.core.pc, dut.core.state);
            $finish;
        end
    end

    integer i;
    initial begin
        rst_n = 0;
        set_bits(1'b0, 1'b0, 1'b0);
        repeat (5) @(posedge clk);
        rst_n = 1;

        repeat (HOLD) @(posedge clk);

        send_byte(8'd8);
        for (i = 0; i < 8; i = i + 1)
            send_byte(prog[i]);

        set_bits(1'b0, 1'b0, 1'b0);
    end
endmodule
