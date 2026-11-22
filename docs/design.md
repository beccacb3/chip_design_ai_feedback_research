# Framework Design

The framework has three goals:

1. **Everything is captured as code/config:** the simulator environment (`Dockerfile`),
   workflow commands (`Makefile`), experiment settings (`configs/`), and data contracts
   (`framework/models.py`).
2. **Change one variable at a time:** each experiment is a short YAML file that points
   to reusable model, prompt, and feedback files, or `extends:` another experiment and
   replaces only the key being tested.
3. **Clear separation between orchestration and evaluation:** `framework/` runs the agent
   loop and dispatches configured checks; `evaluation/` holds the simulator runner,
   reusable testbench checks, and final grading against `designs/.../golden/`.

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
      rtl/              reference Verilog (known-good DUT; 1 or more files)
      tb/               (optional) reference testbench
      mutants/          (optional) buggy RTL files for mutation kill-rate scoring

framework/              agent loop & config-driven orchestration
  models.py             dataclasses (contracts shared across framework and evaluation)
  config.py             loads YAML into ExperimentConfig (`python3 -m framework.config`)
  control_loop.py       outer loop: generate -> testing -> feedback -> fix (`make run`)
  llm.py                OpenRouter API call logic -> LLMCall
  testing.py            dispatcher: reads config.feedback, calls evaluation.testbench
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
- **`EvalResult`** (`final/eval.json`): post-run grading against `golden/` (`compiles`, `golden_rtl_passed`, `mutants_killed`, `mutation_score`, `killed_list`, `survived_list`).
- **`Provenance`** (`provenance.json`): `timestamp`, `git_commit`, `git_dirty`, `docker_image`, `iverilog_version`.
