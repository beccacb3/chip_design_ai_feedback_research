# 4:1 Multiplexer (`mux`)

Source: `ChatDesignVerification/FIXME` (`data/RTLFix/L1/MultiModal/1/1.Multiplexer.pdf`)

## Implement a 4:1 Multiplexer Using Two 2:1 Multiplexers
Design a Verilog module named `mux` that implements a 4:1 multiplexer using two 2:1 multiplexers internally.

## Module Interface
- **Inputs:** `d0`, `d1`, `d2`, `d3` (4 data inputs, 1-bit each), `s1`, `s0` (2 select inputs, 1-bit each)
- **Output:** `y` (1-bit)

## Requirements
- The module should be purely combinational (no registers or clocks).
- Use two internal 2:1 multiplexers.
- Declare internal wires for the outputs of the two 2:1 multiplexers (e.g., `mux1_out`, `mux2_out`).

## Truth Table
| s1 | s0 | mux1_out | mux2_out | y  |
|----|----|----------|----------|----|
| 0  | 0  | d0       | d2       | d0 |
| 0  | 1  | d1       | d3       | d1 |
| 1  | 0  | d0       | d2       | d2 |
| 1  | 1  | d1       | d3       | d3 |

Note: The design must use internal signals `mux1_out` and `mux2_out` to ensure two 2:1 multiplexers are implemented.
