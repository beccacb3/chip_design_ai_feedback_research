# Framework Design

The framework has three goals:

1. **Everything is captured as code/config:** the simulator environment (`Dockerfile`),
   workflow commands (`Makefile`), experiment settings (`configs/`), and data contracts
   (`framework/models.py`).
2. **Change one variable at a time:** each experiment is a short YAML file that points
   to reusable model, prompt, and feedback files, or `extends:` another experiment and
   replaces only the key being tested.
3. **Clear separation between generation and evaluation:** `framework/` runs the agent
   generation loop and writes to a new timestamped folder in `runs/`; `evaluation/`
   grades the finished testbenches against the read-only answer key in
   `designs/.../golden/`.

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
  standardize.py        imports designs into the standard layout and checks them
  <group>/<name>/
    design.yaml         name, top_module, original_name
    spec.md             natural-language specification (given to the agent)
    golden/             answer key (held back for evaluation)
      rtl/              reference Verilog (known-good DUT)
      tb/               (optional) reference testbench
      mutants/          (optional) buggy RTL files for mutation kill-rate scoring

framework/              agent testbench generation flow
  models.py             dataclasses (contracts shared across framework and evaluation)
  config.py             loads YAML into ExperimentConfig (`python3 -m framework.config`)
  control_loop.py       1. orchestrates generate -> test -> feedback -> fix (`make run`)
  llm.py                2. OpenRouter API call logic -> LLMCall
  simulation.py         3. iverilog / vvp / verilator wrapper
  testing.py            4. runs configured in-loop checks -> list[CheckResult]
  feedback.py           5. formats failed CheckResults into prompt text

evaluation/             post-run grading against designs/.../golden/
  evaluate_run.py       grades final.sv -> eval.json + summary.json (`make eval`)
  report.py             aggregates summary.json across runs/ into a table (`make report`)

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
