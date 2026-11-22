# Framework Design

The framework has two jobs:

1. Describe each experiment in one config file, so that a run can be repeated
   and two runs can be compared by looking at what differs between their files.
2. Keep every design (spec + RTL) in the same folder layout, so the code that
   runs experiments only needs to handle one layout.

## Folders

```
configs/
  experiments/   one file per experiment; this is what you run
  models/        which LLM to use and its settings
  feedback/      one file per feedback mechanism (compile, self-check, coverage)
prompts/         prompt text, with {placeholders} filled in at run time
designs/         designs in the standard layout (see below)
framework/
  config.py      reads experiment configs
scripts/
  show_config.py prints an experiment's final config and any problems
  standardize.py imports designs into the standard layout and checks them
```

## Experiment configs

An experiment file lists everything the run uses. Most values are paths to
other files, so a model or feedback mechanism is written once and reused by
many experiments.

```yaml
name: baseline
designs: designs/examples
model: configs/models/gpt4o.yaml
prompts:
  generate: prompts/generate_testbench.md
  find_root_cause: prompts/find_root_cause.md
  fix: prompts/fix_testbench.md
feedback:
  - configs/feedback/compile.yaml
  - configs/feedback/self_check.yaml
max_iterations: 5
seeds: [0, 1, 2]
```

To make a variant, start from another experiment with `extends:` and write
only the keys that change. **A key in the child replaces the same key in the
parent**; that is the only rule.

```yaml
extends: configs/experiments/baseline.yaml
name: no_self_check
feedback:
  - configs/feedback/compile.yaml
```

This makes it easy to change one thing at a time, which the papers in our
report often did not do.

## Design layout

```
designs/<group>/<name>/
  design.yaml   name, top_module, original_name
  spec.md       natural-language specification
  rtl/          the design's Verilog files
  tb/           (optional) reference testbench
```

`scripts/standardize.py check` confirms every design follows this layout: the
folder name is clean (lowercase, underscores), `spec.md` exists and isn't empty,
`rtl/` has Verilog files, and `top_module` is actually defined in them.

`scripts/standardize.py import-verilogeval <folder> <group>` copies VerilogEval
files (`Prob042_vector2_prompt.txt`, `_ref.sv`, `_test.sv`) into this layout
and records the original name in `design.yaml`.

## Not built yet

- The runner that calls the model, runs the feedback tools, and saves results.
- Importers for datasets other than VerilogEval.
