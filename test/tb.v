`default_nettype none
`timescale 1ns / 1ps

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

    tt_um_agila8 user_project (
        .ui_in   (ui_in),
        .uo_out  (uo_out),
        .uio_in  (uio_in),
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
