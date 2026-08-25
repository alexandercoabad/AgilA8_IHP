`default_nettype none
`timescale 1ns/1ps

module tb_bootloader;
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

    // Hold each GPIO level for generously more than one full poll-loop
    // iteration (LW + ADDI + AND + BEQ, each several cycles due to the
    // imem/dmem 1-cycle-latency handshake) so the chip's software
    // polling reliably samples every transition, matching the "not
    // timed, full handshake" protocol build_boot_rom.py describes.
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
            set_bits(b, 1'b1, 1'b1);       // clock high - chip samples DATA
            repeat (HOLD) @(posedge clk);
            set_bits(b, 1'b0, 1'b1);       // clock low - chip waits for this
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

    // Correct AgilA8 ISA assembly sequence (36 bytes total)
    reg [7:0] prog [0:35];
    initial begin
        prog[0]  = 8'h22; prog[1]  = 8'h05; // ADDI r1, r0, 5
        prog[2]  = 8'h24; prog[3]  = 8'h03; // ADDI r2, r0, 3
        prog[4]  = 8'h16; prog[5]  = 8'h50; // ADD  r3, r1, r2

        // Build r4 = 0xF2 (GPIO_DIR) via accumulated ADDI (7*31 + 25 = 242)
        prog[6]  = 8'h28; prog[7]  = 8'h1F; // ADDI r4, r0, 31
        prog[8]  = 8'h29; prog[9]  = 8'h1F; // ADDI r4, r4, 31
        prog[10] = 8'h29; prog[11] = 8'h1F; // ADDI r4, r4, 31
        prog[12] = 8'h29; prog[13] = 8'h1F; // ADDI r4, r4, 31
        prog[14] = 8'h29; prog[15] = 8'h1F; // ADDI r4, r4, 31
        prog[16] = 8'h29; prog[17] = 8'h1F; // ADDI r4, r4, 31
        prog[18] = 8'h29; prog[19] = 8'h1F; // ADDI r4, r4, 31
        prog[20] = 8'h29; prog[21] = 8'h19; // ADDI r4, r4, 25

        // Build r5 = 0x80 (GPIO_DIR[7] enable) via accumulated ADDI (4*31 + 4 = 128)
        prog[22] = 8'h2A; prog[23] = 8'h1F; // ADDI r5, r0, 31
        prog[24] = 8'h2B; prog[25] = 8'h1F; // ADDI r5, r5, 31
        prog[26] = 8'h2B; prog[27] = 8'h1F; // ADDI r5, r5, 31
        prog[28] = 8'h2B; prog[29] = 8'h1F; // ADDI r5, r5, 31
        prog[30] = 8'h2B; prog[31] = 8'h04; // ADDI r5, r5, 4

        // Store r5 (0x80) to [r4] (Write 0x80 to GPIO_DIR at address 0xF2)
        prog[32] = 8'hA5; prog[33] = 8'h00; // SW r5, r4, 0

        // Halt execution
        prog[34] = 8'hF0; prog[35] = 8'h00; // HALT
    end

    integer i;
    integer cyc = 0;
    always @(posedge clk) begin
        cyc = cyc + 1;
        if (cyc > 200000) begin
            $display("TIMEOUT at cycle %0d, pc=0x%04x state=%0d", cyc, dut.core.pc, dut.core.state);
            $finish;
        end
    end

    initial begin
        rst_n = 0;
        set_bits(1'b0, 1'b0, 1'b0);
        repeat (5) @(posedge clk);
        rst_n = 1;

        // Give the chip a little time to reach WAIT_START before we
        // start toggling anything.
        repeat (HOLD) @(posedge clk);

        // Assert START, hold it, then send length byte + program bytes.
        send_byte(8'd36); // length = 36 bytes

        for (i = 0; i < 36; i = i + 1)
            send_byte(prog[i]);

        // Deassert START/DATA/CLOCK - loading should be complete by now.
        set_bits(1'b0, 1'b0, 1'b0);

        // Wait for halted.
        wait (dut.halted == 1);
        $display("HALTED at cycle %0d, pc=0x%04x", cyc, dut.core.pc);

        $display("=== shared_ram CONTENTS (first 36 bytes, DMEM view) ===");
        for (i = 0; i < 36; i = i + 1)
            $display("  shared_ram[%0d] = 0x%02x (expected 0x%02x)", i,
                      dut.shared_ram_inst.mem[i], prog[i]);

        $display("=== REGISTER STATE ===");
        $display("r1=%0d (expect 5)", dut.core.regfile.regs[1]);
        $display("r2=%0d (expect 3)", dut.core.regfile.regs[2]);
        $display("r3=%0d (expect 8)", dut.core.regfile.regs[3]);

        if (dut.core.regfile.regs[1] == 5 && dut.core.regfile.regs[2] == 3
            && dut.core.regfile.regs[3] == 8 && dut.core.pc >= 16'h0080
            && dut.core.pc < 16'h0100)
            $display("RESULT: PASS");
        else
            $display("RESULT: FAIL");

        $finish;
    end
endmodule
