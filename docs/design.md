# Framework Design

This repository implements the experimental pipeline from the
**Phase 2_3 Research Ideation Report**: isolating how increasingly localized,
requirement-specific feedback (`E1` → `E4`) impacts the specification fidelity of
agent-generated hardware testbenches.

## Feedback Experiments (Section 2.3: `E1` → `E4`)

Every experiment uses the same single-agent architecture, model (`configs/models/gpt4o.yaml`),
benchmark designs (`configs/designs/fixme.yaml`), iteration limit (`max_iterations: 5`),
and Section 4.1 final evaluation suite (`configs/final_eval/standard.yaml`). Each
experiment extends the previous one:

| Experiment (`configs/experiments/`) | `extends:` | Spec Format (`feedback`) | In-loop Checks (`testing`) | What Feedback the Agent Receives |
| --- | --- | --- | --- | --- |
| **`e1_monolithic.yaml` (Baseline E1)** | — | Monolithic (`e1_monolithic.yaml`) | `[compile, simulate]` | Monolithic spec + compilation results + simulation pass/fail, assertion failures & runtime errors |
| **`e2_requirement_groups.yaml` (E2)** | `e1_monolithic.yaml` | Decomposed by requirement groups (`e2_requirement_groups.yaml`) | `[compile, simulate, requirement_groups]` | All of E1 + localized simulation pass/fail and assertion failures per requirement group |
| **`e3_req_code_coverage.yaml` (E3)** | `e2_requirement_groups.yaml` | Decomposed by requirement groups | `[compile, simulate, requirement_groups, req_code_coverage]` | All of E2 + RTL code coverage checks per requirement group |
| **`e4_functional_coverage.yaml` (E4)** | `e3_req_code_coverage.yaml` | Decomposed by requirement groups | `[compile, simulate, requirement_groups, req_code_coverage, req_functional_coverage]` | All of E3 + specification-derived functional coverpoint checks per requirement group |

## Final Evaluation Stage (Section 4.1: `4.1.1` – `4.1.7`)

Separate from the in-loop feedback, every finished testbench (`final/testbench.sv`)
is evaluated on the 7 metrics in `configs/final_eval/standard.yaml`:

1. **`golden_tb_comparison` (§4.1.1 FixMe Golden Testbenches):** compares code
   coverage, missed scenarios, and functional coverage against `golden/tb/`, plus
   valid scenarios covered by the generated testbench that `golden/tb/` missed.
2. **`mutation_testing` (§4.1.2 Mutation Testing):** runs `final/testbench.sv`
   against faulty RTL variants in `golden/mutants/` and computes the mutation kill rate.
3. **`golden_rtl_acceptance` (§4.1.3 Golden RTL Acceptance):** verifies that
   `final/testbench.sv` accepts the known-good `golden/rtl/` without false-positive failures.
4. **`computational_cost` (§4.1.4 Computational Cost):** records LLM token usage,
   number of refinement iterations, number of LLM API calls, USD cost, and simulation execution time.
5. **`code_coverage` (§4.1.5 FixMe Testing Utilities / Code Coverage):** measures
   RTL statement/branch coverage on `golden/rtl/`.
6. **`requirement_group_coverage` (§4.1.6 Requirement Group Coverage):** identifies
   which specification requirement groups were / were not exercised.
7. **`functional_coverage` (§4.1.7 Functional Coverage):** evaluates specification-derived
   coverpoints and cross conditions across all requirement groups.

## Repo layout

```
Dockerfile              environment: Python 3.12 + iverilog
Makefile                named commands: image, shell, check, show-config, test, run, eval, report
requirements.txt        pyyaml

configs/
  experiments/          e1_monolithic, e2_requirement_groups, e3_req_code_coverage, e4_functional_coverage
  models/               base.yaml + OpenRouter model configs (gpt4o, claude_sonnet)
  designs/              design sets (examples, fixme)
  simulation/           iverilog simulator settings
  testing/              in-loop checks (compile, simulate, requirement_groups, req_code_coverage, req_functional_coverage)
  feedback/             e1_monolithic (monolithic spec) and e2_requirement_groups (decomposed spec)
  final_eval/           standard.yaml (Section 4.1.1 - 4.1.7 metrics)

prompts/                generate_testbench.md, find_root_cause.md, fix_testbench.md

designs/                ground-truth inputs (read-only during runs)
  standardize.py        imports designs into the standard layout and checks them
  <group>/<name>/
    design.yaml         name, top_module, original_name, requirements (id, description, rtl_lines, coverpoints)
    spec.md             natural-language specification
    golden/             held-back answer key
      rtl/              reference Verilog (known-good DUT)
      tb/               reference golden testbench
      mutants/          faulty RTL variants for mutation testing

framework/              agent loop & config-driven orchestration
  models.py             dataclasses (contracts shared across framework and evaluation)
  config.py             loads YAML into ExperimentConfig (`python3 -m framework.config`)
  control_loop.py       outer loop (iter 0..k) + final evaluation stage (`make run` / `make eval`)
  llm.py                OpenRouter API call logic -> LLMCall
  testing.py            composes `config.testing` (in-loop) and `config.final_eval` (final stage)
  feedback.py           formats failed CheckResults into feedback.md and builds E1 / E2-E4 prompts

evaluation/             simulation, testbench checks, and final-only evaluations
  simulation.py         runs iverilog and vvp
  testbench.py          check_compile, check_simulate, check_requirement_groups, check_req_code_coverage, check_req_functional_coverage, check_mutations
  final.py              eval_golden_tb_comparison, eval_golden_rtl_acceptance, eval_computational_cost
  report.py             aggregates summary.json across runs/ into a Markdown table (`make report`)

tests/                  infrastructure unit & integration test suite (`make test`)
  test_simulation.py
  test_testing_and_feedback.py
  test_control_loop_and_final.py
  test_llm.py
```
