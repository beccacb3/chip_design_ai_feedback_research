You are a hardware verification engineer.

Write a self-checking SystemVerilog testbench for the module `{top_module}`
described by the specification below.

Requirements:
1. Test every behavior and corner case described in the specification.
2. Whenever any check fails, immediately call `$fatal(1, "FAIL: <reason>");` so
   the simulator exits with a non-zero status code.
3. If all checks pass, print `$display("ALL TESTS PASSED");` and call `$finish;`.
4. Return the complete testbench inside a single ```systemverilog code block.

## Specification
{spec}
