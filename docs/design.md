# Framework Design

The framework has three goals:

1. **Everything is captured as code/config:** the simulator environment (`Dockerfile`),
   workflow commands (`Makefile`), experiment settings (`configs/`), and data contracts
   (`framework/models.py`).
2. **Mix-and-match configs with one inheritance rule:** each of the 6 parts of an
   experiment (`model`, `designs`, `simulation`, `testing`, `feedback`, `final_eval`)
   is a small YAML file in `configs/`, and any YAML file can use top-level `extends:`
   to inherit from another file and override specific keys.
3. **Clear separation between orchestration and evaluation:** `framework/` runs the agent
   loop and dispatches configured checks; `evaluation/` holds the simulator runner,
   reusable testbench checks, and final grading against `designs/.../golden/`.

## Repo layout

```
Dockerfile              environment: Python 3.12 + iverilog + verilator
Makefile                named commands: image, shell, check, show-config, run, eval, report
requirements.txt        pyyaml

configs/
  experiments/          top-level experiment files (input to `make run`)
  models/               OpenRouter model id, temperature, max_tokens
  designs/              which design folders to include in a run
  simulation/           simulator tool (iverilog / verilator), args, timeout
  testing/              in-loop checks (compile, simulate, self_check, coverage, spec_check)
  feedback/             repair prompt paths, history strategy (full vs last_only)
  final_eval/           held-out metrics to compute on final/testbench.sv

prompts/                plain .md files with {placeholders}

designs/                ground-truth inputs (read-only during runs)
  standardize.py        imports designs into the standard layout and checks them
  <group>/<name>/
    design.yaml         name, top_module, original_name
    spec.md             natural-language specification (given to the agent)
    golden/             answer key (held back for evaluation)
      rtl/              reference Verilog (known-good DUT; 1 or more files)
      tb/               (optional) reference testbench
      mutants/          (optional) buggy RTL files for mutation kill-rate scoring

framework/              agent loop & config-driven orchestration
  models.py             dataclasses (contracts shared across framework and evaluation)
  config.py             loads YAML into ExperimentConfig (`python3 -m framework.config`)
  control_loop.py       outer loop: generate -> testing -> feedback -> fix (`make run`)
  llm.py                OpenRouter API call logic -> LLMCall
  testing.py            dispatcher: reads config.testing, calls evaluation.testbench
  feedback.py           formats failed CheckResults into feedback.md

evaluation/             simulation, reusable checks, and final grading
  simulation.py         runs iverilog / vvp / verilator, writes sim.log
  testbench.py          check functions: check_compile, check_simulate, check_self_check, ...
  final.py              final grading against golden/rtl + golden/mutants -> final/eval.json
  report.py             aggregates summary.json across runs/ into a table (`make report`)

runs/                   (gitignored) one folder per run, never overwritten
  <experiment>/<timestamp>_<git_sha>/
    config.yaml         snapshot of ExperimentConfig
    provenance.json     Provenance (git commit, dirty flag, docker image, iverilog version)
    summary.json
    <design>__seed<n>/
      run.json          DesignRun (overall tokens, cost, time, and iterations)
      iterations/
        iter_0/
          testbench.sv  TB generated in iter 0
          sim.log       raw iverilog / vvp / verilator output
          checks.json   list of CheckResult
          feedback.md   exact feedback text fed into iter 1's prompt
        iter_1/
          ...
      final/            winning (or last) TB + final grading against golden/
        testbench.sv
        sim.log
        eval.json       EvalResult (Eval0 compile, Eval1 golden pass, Eval2 mutants)
```

## How the 6 config sections map to code (`framework/models.py`)

| Experiment YAML key | Config folder | Dataclass in `models.py` | Module that uses it |
| --- | --- | --- | --- |
| `model` | `configs/models/` | `ModelConfig` | `framework/llm.py` |
| `designs` | `configs/designs/` | `DesignsConfig` | `designs/standardize.py` (`load_design`) |
| `simulation` | `configs/simulation/` | `SimulationConfig` | `evaluation/simulation.py` |
| `testing` | `configs/testing/` | `list[TestingConfig]` | `framework/testing.py` → `evaluation/testbench.py` |
| `feedback` | `configs/feedback/` | `FeedbackConfig` | `framework/feedback.py` |
| `final_eval` | `configs/final_eval/` | `FinalEvalConfig` | `evaluation/final.py` & `evaluation/report.py` |

Why `testing` and `feedback` never get out of sync: every check in
`evaluation/testbench.py` returns a `CheckResult(name, passed, summary)` with
its own self-contained error summary. `framework/feedback.py` simply joins the
`summary` of each failed `CheckResult` and injects it into the repair prompt.
