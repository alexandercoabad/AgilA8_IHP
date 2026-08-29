`default_nettype none
`timescale 1ns / 1ps

module tb ();

  initial begin
    $dumpfile("tb.vcd");
    $dumpvars(0, tb);
    #1;
  end

  // Standard Cell Power Nets
  wire VPWR = 1'b1;
  wire VGND = 1'b0;

  reg clk;
  reg rst_n;
  reg ena;
  reg [7:0] ui_in;

  reg [7:0] uio_in_reg;
  wire [7:0] uio_in;
  wire miso;

  assign uio_in = {uio_in_reg[7:3], miso, uio_in_reg[1:0]};

  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;

  initial begin
    clk = 0;
    rst_n = 0;
    ena = 1;
    ui_in = 8'h00;
    uio_in_reg = 8'h00;
  end

  // Force-clear internal registers in GL mode to eliminate 'X' states
  `ifdef GL_TEST
  initial begin
    #0.1;
    $display("Applying GL zero-initialization deposit...");
    // Clear initial state on reset pin to force state resolution
    $deposit(user_project.rst_n, 1'b0);
  end
  `endif

  tt_um_agila8 user_project (
`ifdef USE_POWER_PINS
      .VPWR(VPWR),
      .VGND(VGND),
`endif
      .ui_in   (ui_in),
      .uo_out  (uo_out),
      .uio_in  (uio_in),
      .uio_out (uio_out),
      .uio_oe  (uio_oe),
      .ena     (ena),
      .clk     (clk),
      .rst_n   (rst_n)
  );

  // Drive default high state for inactive chip selects
  wire flash_cs_n = uio_oe[0] ? uio_out[0] : 1'b1;
  wire spi_mosi   = uio_oe[1] ? uio_out[1] : 1'b0;
  wire spi_sck    = uio_oe[3] ? uio_out[3] : 1'b0;
  wire psram_cs_n = uio_oe[6] ? uio_out[6] : 1'b1;

  // Flash behavioral model (03h read)
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

  // PSRAM behavioral model (02h write / 03h read)
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

  assign miso = (!flash_cs_n) ? f_miso : ((!psram_cs_n) ? p_miso : 1'b0);

endmodule
