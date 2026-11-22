
`timescale 1ns/1ps

module alu_select_tb;

  reg [16:0] controls;
  wire [16:0] outputs;

  alu_select dut (
    .ctl_alu_oe(controls[0]),
    .ctl_alu_shift_oe(controls[1]),
    .ctl_alu_op2_oe(controls[2]),
    .ctl_alu_res_oe(controls[3]),
    .ctl_alu_op1_oe(controls[4]),
    .ctl_alu_bs_oe(controls[5]),
    .ctl_alu_op1_sel_bus(controls[6]),
    .ctl_alu_op1_sel_low(controls[7]),
    .ctl_alu_op1_sel_zero(controls[8]),
    .ctl_alu_op2_sel_zero(controls[9]),
    .ctl_alu_op2_sel_bus(controls[10]),
    .ctl_alu_op2_sel_lq(controls[11]),
    .ctl_alu_sel_op2_neg(controls[12]),
    .ctl_alu_sel_op2_high(controls[13]),
    .ctl_alu_core_R(controls[14]),
    .ctl_alu_core_V(controls[15]),
    .ctl_alu_core_S(controls[16]),

    .alu_oe(outputs[0]),
    .alu_shift_oe(outputs[1]),
    .alu_op2_oe(outputs[2]),
    .alu_res_oe(outputs[3]),
    .alu_op1_oe(outputs[4]),
    .alu_bs_oe(outputs[5]),
    .alu_op1_sel_bus(outputs[6]),
    .alu_op1_sel_low(outputs[7]),
    .alu_op1_sel_zero(outputs[8]),
    .alu_op2_sel_zero(outputs[9]),
    .alu_op2_sel_bus(outputs[10]),
    .alu_op2_sel_lq(outputs[11]),
    .alu_sel_op2_neg(outputs[12]),
    .alu_sel_op2_high(outputs[13]),
    .alu_core_R(outputs[14]),
    .alu_core_V(outputs[15]),
    .alu_core_S(outputs[16])
  );

  task check_mapping;
    begin
      #1;
      if (outputs !== controls) begin
        $display("FAIL: inputs=%b outputs=%b",
                 controls, outputs);
        $fatal(1, "ALU control mapping mismatch");
      end
    end
  endtask

  integer i;

  initial begin
    // All inputs low
    controls = 17'b0;
    check_mapping();

    // All inputs high
    controls = {17{1'b1}};
    check_mapping();

    // Walking-one pattern: check each mapping independently
    for (i = 0; i < 17; i = i + 1) begin
      controls = 17'b1 << i;
      check_mapping();
    end

    // Walking-zero pattern
    for (i = 0; i < 17; i = i + 1) begin
      controls = {17{1'b1}} ^ (17'b1 << i);
      check_mapping();
    end

    // Alternating patterns
    controls = 17'b10101010101010101;
    check_mapping();

    controls = 17'b01010101010101010;
    check_mapping();

    $display("ALL ALU_SELECT TESTS PASSED");
    $finish;
  end

endmodule
