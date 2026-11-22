
`timescale 1ns/1ps

module counter4_tb;

    reg clk = 0;
    reg reset = 0;
    reg en = 0;
    wire [3:0] q;

    counter4 dut (
        .clk(clk),
        .reset(reset),
        .en(en),
        .q(q)
    );

    always #5 clk = ~clk;

    task check_q(input [3:0] expected);
        begin
            if (q !== expected) begin
                $display("FAIL: expected %d, got %d", expected, q);
                $fatal(1, "Counter mismatch");
            end
        end
    endtask

    initial begin
        // 1. Synchronous reset
        reset = 1;
        @(posedge clk);
        #1;
        check_q(0);

        // 2. Increment when enabled
        @(negedge clk);
        reset = 0;
        en = 1;

        repeat (3) @(posedge clk);
        #1;
        check_q(3);

        // 3. Hold when disabled
        @(negedge clk);
        en = 0;
        repeat (3) @(posedge clk);
        #1;
        check_q(3);

        // 4. Wrap around after 16 increments
        @(negedge clk);
        reset = 1;
        @(posedge clk);
        #1;
        check_q(0);

        @(negedge clk);
        reset = 0;
        en = 1;
        repeat (16) @(posedge clk);
        #1;
        check_q(0);

        $display("ALL COUNTER4 TESTS PASSED");
        $finish;
    end

endmodule
