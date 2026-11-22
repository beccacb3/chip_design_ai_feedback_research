module counter4 (
    input  wire       clk,
    input  wire       reset,
    input  wire       en,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (reset) q <= 4'd0;
        else       q <= q + 4'd1;     // bug: ignores enable signal
    end
endmodule
