module syncrstz(
    input  wire rstz,
    input  wire clk,
    input  wire iscanmode,
    input  wire iscanrstz,
    output wire srstz
);
parameter RSYNCDEPTH = 2;
reg [RSYNCDEPTH:0] regrstz;
wire wscanrstz;
assign wscanrstz = (iscanmode) ? iscanrstz : rstz;
always @(posedge clk or negedge wscanrstz)
  if (!wscanrstz)
    regrstz[0] <= 0;
  else
    regrstz[0] <= 1'b1;
always @(posedge clk)
  regrstz[RSYNCDEPTH:1] <= regrstz[RSYNCDEPTH-1:0];
wire wsrstz;
assign wsrstz = &regrstz[RSYNCDEPTH:0];
assign srstz = (iscanmode) ? iscanrstz : wsrstz;
endmodule
