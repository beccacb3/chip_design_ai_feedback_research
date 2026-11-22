# Framework Design (proposal)

Status: **draft for discussion**. Nothing here is final; push back on any of it.

## Goals

The critique report found three recurring problems in the paper set:

1. Papers change several things at once, so you can't tell which architectural
   change caused the improvement (CorrectBench, AutoBench).
2. Cost and time are rarely reported (~28% of papers).
3. Results are hard to reproduce (missing skill/reference libraries, model drift).

So the framework is built around one idea: **every experiment is a config file
that composes small, swappable pieces**, and every run snapshots the fully
resolved config next to its outputs. Changing one variable means swapping one
reference, which makes ablations and "gradient of variable" sweeps cheap.

## Directory layout

```
configs/
  experiments/   # top-level entry points; the only thing you pass to the runner
  agents/        # agent architecture (control loop, stages, context, tools)
  models/        # inference engine (provider, model id, sampling params)
  feedback/      # one file per feedback mechanism (compile, sim, coverage, mutation...)
  evals/         # metrics to compute after a run
  suites/        # which designs to run on (list / filters over designs/)
  importers/     # rules for turning a raw external dataset into designs/
prompts/
  generation/    # prompt templates, plain Markdown with {placeholders}
  correction/
  feedback/      # templates that format tool output back into the context
designs/
  <suite>/<design_id>/
    design.yaml  # metadata (see below)
    spec.md      # natural-language specification
    rtl/         # golden RTL (DUT)
    golden_tb/   # optional reference testbench
    mutants/     # optional mutated RTL for kill-rate evals
  manifest.yaml  # generated index of all designs (scripts/standardize.py index)
raw/             # (gitignored) untouched downloads of external datasets
runs/            # (gitignored) outputs: runs/<experiment>/<timestamp>/...
scripts/
  standardize.py # import / check / index content
src/specfidelity/
  config.py      # config loader (extends, refs, overrides, sweeps, validation)
  __main__.py    # CLI: resolve / plan  (runner comes later)
```

## Config model

Configs are YAML. Three mechanisms keep them reusable:

| Mechanism | Syntax | Purpose |
| --- | --- | --- |
| **Reference** | any string value ending in `.yaml`/`.yml` | Inlines that file. Lets an experiment point at an agent, model, suite, etc. |
| **Extends** | `extends: path/to/base.yaml` | Deep-merges this file over a base. Dicts merge; lists and scalars replace. Use for ablations. |
| **Sweep** | `sweep: {dotted.key: [v1, v2, ...]}` | Cartesian expansion into multiple run variants. |

Plus CLI overrides (`-o budget.max_iterations=10`) and `${dotted.key}`
interpolation inside strings (e.g. `output_dir: runs/${name}`).

All paths are **relative to the repo root**, not to the file that contains
them. That makes a path mean the same thing wherever it appears.

Resolution order: load + `extends` → CLI overrides → sweep expansion →
reference inlining → interpolation → validation (required keys and file
existence).

### Experiment (entry point)

```yaml
name: correctbench_gpt4o
suite:  configs/suites/examples.yaml
agent:  configs/agents/correctbench.yaml
model:  configs/models/gpt4o.yaml
feedback:                      # ordered; agent stages refer to these by name
  - configs/feedback/compile.yaml
  - configs/feedback/functional_self_check.yaml
eval:   configs/evals/default.yaml
budget: { max_iterations: 5, max_reboots: 2, max_tokens: 200000, max_wall_s: 900 }
seeds:  [0, 1, 2]
output_dir: runs/${name}
```

### Agent

Structured around the five components from Section 3.1 of the report so that
architectures can be compared component by component:

```yaml
name: correctbench
control_loop: { type: generate_validate_correct }
stages:
  - { id: generate, prompt: prompts/generation/testbench_from_spec.md }
  - { id: validate, feedback: [compile, functional_self_check] }
  - { id: correct,  prompts: [prompts/correction/root_cause.md, prompts/correction/apply_fix.md] }
context: { strategy: full_history }   # or prune_last_k, summarize, ...
tools: [simulator]
```

The model (inference engine) is deliberately **not** part of the agent, so the
same architecture can be run across backends.

### Feedback mechanism

One file per mechanism. `kind` selects the implementation; `template` decides
how the result is written back into the context.

```yaml
name: compile
kind: compile
tool: { name: iverilog, args: ["-g2012"] }
template: prompts/feedback/compile_errors.md
```

Planned kinds: `compile`, `simulate`, `functional_self_check` (CorrectBench-style
RTL-ensemble validation), `coverage` (line/branch/toggle/functional),
`mutation` (kill rate), `spec_trace` (GoGoTB-style spec-grounded bins).

### Eval

Lists metrics computed after the run. Cost/time are always on, to address the
gap noted in Section 5 of the report.

### Design metadata (`designs/<suite>/<id>/design.yaml`)

```yaml
id: counter4                 # canonical, snake_case, == directory name
suite: examples
top_module: counter4         # must match `module` in rtl/
circuit_type: sequential     # combinational | sequential
spec: spec.md
rtl: [rtl/counter4.v]
golden_tb: []                # optional
mutants: []                  # optional
source: { dataset: hand_written, original_name: counter4 }
aliases: []                  # other names this design is known by
```

## `scripts/standardize.py`

There are three subcommands. Each one is a dry run unless you pass `--apply`.

- **`import <raw_dir> --importer configs/importers/<x>.yaml --suite <name>`**
  Matches files with the importer's regex rules, normalizes names into canonical
  ids (e.g. `Prob042_vector2_prompt.txt` → `vector2/spec.md`), copies them into
  `designs/<suite>/<id>/`, and writes `design.yaml` with the original names kept
  under `source` and `aliases`. Raw files are copied, never moved.
- **`check`** validates every `design.yaml`: the id matches the directory, the
  referenced files exist, `top_module` matches the RTL, ids are unique after
  normalization across suites, and the spec isn't empty. It also resolves every
  experiment config so broken references show up early. It exits non-zero on
  errors, so it can run in CI or a pre-commit hook.
- **`index`** regenerates `designs/manifest.yaml`.

## Open questions / decisions for us

1. **Custom loader vs Hydra/OmegaConf.** Hydra already does composition,
   sweeps, and overrides, but it's heavy and opinionated (cwd changes, the
   `defaults` list). The custom loader is about 150 lines on top of PyYAML. My
   recommendation is to start custom and switch if it grows.
2. **Should paths be relative to the repo root or to the file?** I chose the
   repo root. It's simpler to read, but configs can't be moved without
   rewriting their paths.
3. **Prompt format.** Plain `.md` with `{placeholders}`, or Jinja2 (which adds
   conditionals and loops but is another dependency)?
4. **Run outputs.** Should runs go in local `runs/` only, or should we also log
   to something like W&B or MLflow? At minimum we need a `resolved_config.yaml`,
   per-iteration transcripts, token counts, and wall time.
5. **Which datasets do we import first?** VerilogEval-Human (the AutoBench and
   CorrectBench baseline) is the obvious choice. The importer config for it is
   included as an example.
