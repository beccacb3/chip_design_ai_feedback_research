# Framework Design

The framework has three goals:

1. **Everything is captured as code/config:** the simulator environment (`Dockerfile`),
   workflow commands (`Makefile`), experiment settings (`configs/`), and data contracts
   (`framework/models.py`).
2. **Change one variable at a time:** each experiment is a short YAML file that points
   to reusable model, prompt, and feedback files, or `extends:` another experiment and
   replaces only the key being tested.
3. **Clear separation between ground truth and generated outputs:** reference answers
   live in `designs/.../golden/` (read-only), while every run writes to a new
   timestamped folder in `runs/` that is never overwritten.

## Repo layout

```
Dockerfile              environment: Python 3.12 + iverilog + verilator
Makefile                named commands: image, shell, check, show-config, run, eval, report
requirements.txt        pyyaml

configs/
  experiments/          one file per experiment (input to `make run`)
  models/               OpenRouter model id, temperature, max_tokens
  feedback/             in-loop checks (compile, simulate, self_check, coverage, spec_check)

prompts/                plain .md files with {placeholders}

designs/                ground-truth inputs (read-only during runs)
  <group>/<name>/
    design.yaml         name, top_module, original_name
    spec.md             natural-language specification (given to the agent)
    golden/             answer key (held back for evaluation)
      rtl/              reference Verilog (known-good DUT)
      tb/               (optional) reference testbench
      mutants/          (optional) buggy RTL files for mutation kill-rate scoring

framework/
  models.py             dataclasses for all configs, designs, LLM calls, and run records
  config.py             loads YAML into ExperimentConfig

scripts/
  standardize.py        imports designs into the standard layout and checks them
  show_config.py        prints the resolved ExperimentConfig and checks paths

runs/                   (gitignored) one folder per run, never overwritten
  <experiment>/<timestamp>_<git_sha>/
    config.yaml         snapshot of ExperimentConfig
    provenance.json     Provenance (git commit, dirty flag, docker image, iverilog version)
    summary.json
    <design>__seed<n>/
      run.json          DesignRun (all iterations, LLM calls, and feedback CheckResults)
      eval.json         EvalResult (scored against designs/.../golden/)
      generated_tb/
        iter_0.sv
        iter_1.sv
        final.sv
```

## Contracts (`framework/models.py`)

Every YAML/JSON file on disk and every boundary between modules matches a
standard-library `@dataclass` in `framework/models.py`:

- **`ModelConfig`** (`configs/models/*.yaml`): `name`, `model_id` (OpenRouter id), `temperature`, `max_tokens`.
- **`FeedbackConfig`** (`configs/feedback/*.yaml`): `name`, `tool`, `args`, `options`.
- **`ExperimentConfig`** (`configs/experiments/*.yaml`): `name`, `designs`, `model`, `prompts`, `feedback`, `max_iterations`, `seeds`.
- **`Design`** (`designs/<group>/<name>/`): `name`, `top_module`, `original_name`, `spec_path`, `golden_rtl`, `golden_tb`, `golden_mutants`.
- **`LLMCall`**: exact prompt, raw response, token counts, cost (USD), and wall time.
- **`CheckResult`**: result of one feedback check (`name`, `passed`, `summary`, `details`).
- **`Iteration`** & **`DesignRun`** (`run.json`): every iteration's testbench, LLM calls, check results, and total cost/time.
- **`EvalResult`** (`eval.json`): post-run grading against `golden/` (`compiles`, `golden_rtl_passed`, `mutants_killed`, `mutation_score`, `killed_list`, `survived_list`).
- **`Provenance`** (`provenance.json`): `timestamp`, `git_commit`, `git_dirty`, `docker_image`, `iverilog_version`.

## In-loop feedback vs. post-run evaluation

- **In-loop feedback (`configs/feedback/`):** checks the agent can run while generating
  and fixing its testbench (`compile`, `simulate`, `self_check`, `coverage`, `spec_check`).
  These never use `golden/tb/` or `golden/mutants/` to tell the agent which outputs are wrong.
- **Post-run evaluation (`EvalResult`):** after the agent finishes, `final.sv` is graded
  against `golden/rtl/` (Eval0 compile, Eval1 false-positive check) and `golden/mutants/`
  (Eval2 mutation kill rate).
