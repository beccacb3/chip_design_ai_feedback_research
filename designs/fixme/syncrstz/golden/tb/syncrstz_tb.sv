`timescale 1ns/1ps

module tb_top;
    reg  rstz, clk, iscanmode, iscanrstz;
    wire srstz;

    syncrstz dut (
        .rstz(rstz),
        .clk(clk),
        .iscanmode(iscanmode),
        .iscanrstz(iscanrstz),
        .srstz(srstz)
    );

    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        // Normal mode: assert async reset, then release and verify 3-posedge latency
        iscanmode = 0; iscanrstz = 1; rstz = 0;
        #3;
        if (srstz !== 1'b0) $fatal(1, "FAIL: srstz should be 0 during async reset");
        rstz = 1;
        @(posedge clk); #1;
        if (srstz !== 1'b0) $fatal(1, "FAIL: srstz released too early (cycle 1)");
        @(posedge clk); #1;
        if (srstz !== 1'b0) $fatal(1, "FAIL: srstz released too early (cycle 2)");
        @(posedge clk); #1;
        if (srstz !== 1'b1) $fatal(1, "FAIL: srstz did not release after RSYNCDEPTH+1 posedges");

        // Scan mode bypass: srstz must immediately follow iscanrstz
        iscanmode = 1; iscanrstz = 0; #1;
        if (srstz !== 1'b0) $fatal(1, "FAIL: scan mode bypass low failed");
        iscanrstz = 1; #1;
        if (srstz !== 1'b1) $fatal(1, "FAIL: scan mode bypass high failed");

        $display("TESTBENCH_PASSED");
        $finish;
    end
endmodule
