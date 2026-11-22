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
   loop and composes checks/evaluations; `evaluation/` holds the simulator runner,
   single-testbench checks (`testbench.py`), and final-only evaluations (`final.py`).

## Repo layout

```
Dockerfile              environment: Python 3.12 + iverilog
Makefile                named commands: image, shell, check, show-config, test, run, eval, report
requirements.txt        pyyaml

configs/
  experiments/          experiment levels (baseline, level1_compile .. level4_mutations)
  models/               base.yaml + OpenRouter model configs (gpt4o, claude_sonnet)
  designs/              which design folders to include in a run (examples, fixme)
  simulation/           simulator tool (iverilog), args, timeout
  testing/              in-loop checks (compile, simulate, coverage, mutations)
  feedback/             repair prompt paths, history strategy (full vs last_only)
  final_eval/           metrics composed in the final stage (testbench + final-only evals)

prompts/                plain .md files with {placeholders}

designs/                ground-truth inputs (read-only during runs)
  standardize.py        imports designs into the standard layout and checks them
  <group>/<name>/
    design.yaml         name, top_module, original_name
    spec.md             natural-language specification (given to the agent)
    golden/             answer key (held back for evaluation)
      rtl/              reference Verilog (known-good DUT; 1 or more files)
      tb/               (optional) reference testbench
      mutants/          buggy RTL files for mutation kill-rate scoring

framework/              agent loop & config-driven orchestration
  models.py             dataclasses (contracts shared across framework and evaluation)
  config.py             loads YAML into ExperimentConfig (`python3 -m framework.config`)
  control_loop.py       outer loop (iter 0..k) + final evaluation stage (`make run` / `make eval`)
  llm.py                OpenRouter API call logic -> LLMCall
  testing.py            composes `config.testing` (in-loop) and `config.final_eval` (final stage)
  feedback.py           formats failed CheckResults into feedback.md and builds prompts

evaluation/             simulation, testbench checks, and final-only evaluations
  simulation.py         runs iverilog and vvp
  testbench.py          single-TB checks: check_compile, check_simulate, check_coverage, check_mutations
  final.py              final-only evals: eval_false_positive, eval_turns, eval_cost_and_time, eval_assertion_audit
  report.py             aggregates summary.json across runs/ into a Markdown table (`make report`)

tests/                  infrastructure unit & integration test suite (`make test`)
  test_simulation.py
  test_testing_and_feedback.py
  test_control_loop_and_final.py
  test_llm.py

runs/                   (gitignored) one folder per run, never overwritten
  <experiment>/<timestamp>_<git_sha>/
    config.yaml         snapshot of ExperimentConfig
    provenance.json     Provenance (git commit, dirty flag, docker image, iverilog version)
    summary.json        experiment-wide rollup metrics
    <design>__seed<n>/
      run.json          DesignRun (overall tokens, cost, time, and iterations)
      iterations/
        iter_0/
          testbench.sv  TB generated in iter 0
          llm_calls.json
          compile.log / sim.log / coverage.json / mutations.json
          checks.json   list of CheckResult
          feedback.md   exact feedback text fed into iter 1's prompt
        iter_1/
          ...
      final/            winning (or last) TB + composed final evaluation scorecard
        testbench.sv
        eval.json       EvalResult
```

## Experiment levels (`configs/experiments/`)

| Experiment file | `max_iterations` | In-loop `testing` checks | What it tests |
| --- | :---: | --- | --- |
| `baseline.yaml` | 1 | `[]` (none) | Level 0: 1-shot LLM testbench generation with no feedback |
| `level1_compile.yaml` | 5 | `[compile]` | Level 1: compiler error feedback only |
| `level2_simulate.yaml` | 5 | `[compile, simulate]` | Level 2: compilation + simulation pass on reference RTL |
| `level3_coverage.yaml` | 5 | `[compile, simulate, coverage]` | Level 3: adds RTL statement/branch coverage feedback |
| `level4_mutations.yaml` | 5 | `[compile, simulate, coverage, mutations]` | Level 4: adds mutation kill-rate feedback |

Every experiment runs the exact same composed `final_eval` stage at the end
(`compile`, `simulate`, `coverage`, `mutations`, `false_positive`, `turns`,
`cost_and_time`, `assertion_audit`) so all levels are compared on the same
scorecard.
