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
  prompts/       # prompt configs (template + vars + role/system), inheritable
  agents/        # agent architecture (control loop, stages, context, tools)
  models/        # inference engine (provider, model id, sampling params)
  feedback/      # one file per feedback mechanism (compile, sim, coverage, mutation...)
  evals/         # metrics to compute after a run
  suites/        # which designs to run on (list / filters over designs/)
  importers/     # rules for turning a raw external dataset into designs/
prompts/         # raw template text only (Markdown with {placeholders});
                 # always used through a configs/prompts/ config
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
  config.py      # config loader (composition, inheritance, overrides, sweeps, validation)
  __main__.py    # CLI: resolve / plan  (runner comes later)
```

## Config model: composition + inheritance

Every piece of the flow is a **component config** with a `kind`:
`prompt`, `agent`, `model`, `feedback`, `eval`, or `suite`. An experiment
composes components, and components compose other components (an agent's
stages reference prompt configs; a feedback mechanism references the prompt
config used to report its result). Define something once, reuse it everywhere.

Wherever a config is expected, you can write it three ways:

```yaml
# 1. Reuse as-is: a path to an already defined config
prompt: configs/prompts/generation/tb_from_spec.yaml

# 2. Reuse + tweak: inherit from it and override some fields, inline
prompt:
  extends: configs/prompts/generation/tb_from_spec.yaml
  vars: { language: SystemVerilog }

# 3. Inline from scratch (rarely needed)
prompt: { kind: prompt, name: adhoc, template: prompts/generation/x.md }
```

A file can also `extends:` another file at the top level to make a named,
reusable variant (e.g. `tb_from_spec_python_checker.yaml` extends
`tb_from_spec.yaml` and changes one var).

### Merge rules

- Mappings merge recursively; lists and scalars replace.
- `null` deletes a key. This is how ablations remove things:
  `feedback: { functional_self_check: null }`.
- If the base value is still a reference (`prompt: x.yaml`) and the override is
  a mapping without `extends`, the override is applied **on top of** `x.yaml`
  rather than replacing it. So in an experiment you can reach into the agent's
  prompt without restating anything:

  ```yaml
  extends: configs/experiments/correctbench_gpt4o.yaml
  agent:
    stages:
      generate:
        prompt:
          vars: { language: SystemVerilog }
  ```
- Things meant to be tweaked individually are **mappings keyed by name**, not
  lists: agent `stages` (keyed by stage id, in execution order) and experiment
  `feedback` (keyed by mechanism name). That is what lets inheritance change
  one stage or drop one mechanism.
- `abstract: true` marks a config that only exists to be inherited from (e.g.
  `configs/prompts/base.yaml`); it is not inherited by children.

CLI overrides (`-o agent.stages.generate.prompt.vars.language=VHDL`) and
`sweep:` keys use the same dotted paths and pass straight through references
(`agent` being a path does not stop you from overriding something inside it).
`${dotted.key}` interpolation works inside strings (e.g. `output_dir: runs/${name}`).

All paths are **relative to the repo root**, not to the file containing them.

Resolution order: load + top-level `extends` → CLI overrides → sweep expansion →
reference/`extends` inlining (recursive) → interpolation → validation. Every
inlined config gets a `_source` field recording where it came from (and whether
it was locally overridden), so the resolved snapshot is self-describing.

### Prompt

```yaml
# configs/prompts/generation/tb_from_spec.yaml
extends: configs/prompts/base.yaml          # role: user, system prompt, ...
name: tb_from_spec
template: prompts/generation/testbench_from_spec.md
vars:                                       # defaults baked into this prompt
  language: Verilog
  checker_style: inline Verilog comparisons against expected values
required_vars: [top_module, spec, interface] # supplied at run time
```

Validation checks every `{placeholder}` in the template is either in `vars` or
`required_vars` (catches typos), and warns about required vars the template
never uses.

### Experiment (entry point)

```yaml
name: correctbench_gpt4o
suite:  configs/suites/examples.yaml
agent:  configs/agents/correctbench.yaml
model:  configs/models/gpt4o.yaml
feedback:                       # name -> config; null disables
  compile: configs/feedback/compile.yaml
  functional_self_check: configs/feedback/functional_self_check.yaml
eval:   configs/evals/default.yaml
budget: { max_iterations: 5, max_reboots: 2, max_tokens: 200000, max_wall_s: 900 }
seeds:  [0, 1, 2]
output_dir: runs/${name}
```

Examples in `configs/experiments/`:

| File | Shows |
| --- | --- |
| `correctbench_gpt4o.yaml` | baseline |
| `ablation_no_self_check.yaml` | inherit + remove a feedback mechanism with `null` |
| `ablation_python_checker.yaml` | inherit + swap one stage's prompt for another defined prompt |
| `ablation_prompt_language.yaml` | inherit + override one var of the existing prompt, inline |
| `sweep_models_iterations.yaml` | sweep over models x budgets x prompt configs (12 variants) |

### Agent

Structured around the five components from Section 3.1 of the report so that
architectures can be compared component by component:

```yaml
kind: agent
name: correctbench
control_loop: { type: generate_validate_correct }
stages:
  generate: { prompt: configs/prompts/generation/tb_from_spec.yaml }
  validate: { feedback: all }          # whatever the experiment enables
  correct:
    prompts:
      - configs/prompts/correction/root_cause.yaml
      - configs/prompts/correction/apply_fix.yaml
context: { strategy: full_history }    # or prune_last_k, summarize, ...
tools: [simulator]
```

`configs/agents/autobench.yaml` is just `extends: correctbench.yaml` plus a
different generation prompt. The model (inference engine) is deliberately
**not** part of the agent, so the same architecture runs across backends.

### Feedback mechanism

One file per mechanism. `type` selects the implementation; `template` is a
prompt config deciding how the result is written back into the context.
Variants inherit (`compile_verilator.yaml` extends `compile.yaml`, swaps the tool).

```yaml
kind: feedback
name: compile
type: compile
tool: { name: iverilog, args: ["-g2012"] }
template: configs/prompts/feedback/compile_errors.yaml
```

Planned types: `compile`, `simulate`, `functional_self_check` (CorrectBench-style
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
  normalization across suites, and the spec isn't empty. It then validates
  every component config under `configs/` on its own (`kind`, required keys,
  template placeholders vs. vars) and resolves every experiment and sweep
  variant, so broken references show up early. Identical problems are reported
  once with a count rather than once per experiment that inherits them. It
  exits non-zero on errors, so it can run in CI or a pre-commit hook.
- **`index`** regenerates `designs/manifest.yaml`.

## Open questions / decisions for us

1. ~~Custom loader vs Hydra/OmegaConf.~~ **Decided: custom loader** built
   around composition and inheritance: any component can be referenced by
   path, extended, and tweaked inline (see "Config model").
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
