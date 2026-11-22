You are a hardware verification engineer decomposing a hardware specification
into requirement groups for specification-grounded testbench verification.

Given the specification and the numbered reference RTL for `{top_module}` below,
decompose the specification into 3 to 5 distinct requirement groups.

Return ONLY a ```yaml code block with a top-level `requirements:` list where
each item has:
- `id`: uppercase identifier starting with `REQ_` (e.g. `REQ_RESET`)
- `description`: one-sentence summary of the requirement
- `rtl_lines`: list of 1-indexed integer line numbers in the reference RTL that
  implement this requirement (only executable `assign` or procedural assignment
  lines inside `always` blocks)
- `coverpoints`: mapping of 1 or 2 short scenario names (`snake_case`) to valid
  Verilog boolean expressions over the module's ports/signals that evaluate to
  true when that requirement scenario is exercised (use `===` or `!==`, e.g.
  `"reset === 1'b1 && q === 4'd0"`)

## Specification
{spec}

## Numbered Reference RTL
{numbered_rtl}
