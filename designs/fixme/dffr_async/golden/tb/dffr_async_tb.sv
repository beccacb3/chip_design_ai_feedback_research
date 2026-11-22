
`timescale 1ns/1ps

module dffr_async_tb;

  reg clk = 0;
  reg rst = 0;
  reg se = 0;
  reg din = 0;
  reg si = 0;

  wire q;
  wire so;

  dffr_async dut (
    .din(din),
    .clk(clk),
    .rst(rst),
    .q(q),
    .se(se),
    .si(si),
    .so(so)
  );

  task check_output(input expected);
    begin
      #1;
      if (q !== expected || so !== expected) begin
        $display("FAIL: expected=%b q=%b so=%b",
                 expected, q, so);
        $fatal(1, "Output mismatch");
      end
    end
  endtask

  initial begin
    // Test 1: Asynchronous reset
    rst = 1;
    check_output(0);

    // Test 2: Normal data capture
    rst = 0;
    din = 1;
    #5 clk = 1;
    check_output(1);

    // Test 3: Scan mode
    clk = 0;
    se = 1;
    si = 0;
    #5 clk = 1;
    check_output(0);

    // Test 4: Return to normal mode
    clk = 0;
    se = 0;
    din = 1;
    #5 clk = 1;
    check_output(1);

    $display("ALL DFFR_ASYNC TESTS PASSED");
    $finish;
  end

endmodule
