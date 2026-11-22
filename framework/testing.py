"""Test & evaluation composer:
  1. `run_iteration_checks` composes `config.testing` (from `evaluation.testbench`)
     for each iteration `iterations/iter_<k>/`.
  2. `run_final_evaluations` composes `config.final_eval.metrics` using a
     combination of single-testbench checks (`evaluation.testbench`) and
     final-only evaluations (`evaluation.final`) for `final/eval.json`.
"""

from dataclasses import asdict
import json
from pathlib import Path

from evaluation import final as final_evals
from evaluation import testbench
from framework.models import (
    CheckResult,
    Design,
    DesignRun,
    EvalResult,
    FinalEvalConfig,
    SimulationConfig,
    TestingConfig,
)

TESTBENCH_CHECKS = {
    "compile": testbench.check_compile,
    "simulate": testbench.check_simulate,
    "mutations": testbench.check_mutations,
    "coverage": testbench.check_coverage,
}

FINAL_ONLY_EVALS = {
    "false_positive": final_evals.eval_false_positive,
    "turns": final_evals.eval_turns,
    "cost_and_time": final_evals.eval_cost_and_time,
    "assertion_audit": final_evals.eval_assertion_audit,
}


def run_iteration_checks(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    testing_configs: list[TestingConfig],
) -> list[CheckResult]:
    """Run each configured test in `testing_configs` and write iter_dir/checks.json."""
    iter_dir = Path(iter_dir)
    iter_dir.mkdir(parents=True, exist_ok=True)

    results: list[CheckResult] = []
    for cfg in testing_configs:
        if cfg.name not in TESTBENCH_CHECKS:
            raise ValueError(f"unknown testing check: {cfg.name}")
        result = TESTBENCH_CHECKS[cfg.name](design, tb_path, iter_dir, sim, cfg)
        results.append(result)
        # If compilation failed, skip downstream runtime checks for this iteration.
        if cfg.name == "compile" and not result.passed:
            break

    (iter_dir / "checks.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2) + "\n"
    )
    return results


def run_final_evaluations(
    design: Design,
    design_run: DesignRun,
    design_run_dir: Path,
    sim: SimulationConfig,
    final_cfg: FinalEvalConfig,
) -> EvalResult:
    """Compose `final_cfg.metrics` (testbench checks + final-only evaluations) on `final/testbench.sv`."""
    design_run_dir = Path(design_run_dir)
    final_dir = design_run_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_tb = design_run_dir / design_run.final_testbench

    by_name: dict[str, CheckResult] = {}
    ordered_checks: list[CheckResult] = []

    # 1. Run any single-testbench checks requested in final_cfg.metrics
    for metric in final_cfg.metrics:
        if metric in TESTBENCH_CHECKS:
            res = TESTBENCH_CHECKS[metric](
                design, final_tb, final_dir, sim, TestingConfig(name=metric)
            )
            by_name[metric] = res
            ordered_checks.append(res)

    # 2. Run any final-only evaluations requested in final_cfg.metrics
    for metric in final_cfg.metrics:
        if metric in FINAL_ONLY_EVALS:
            res = FINAL_ONLY_EVALS[metric](design_run, design_run_dir, by_name)
            by_name[metric] = res
            ordered_checks.append(res)
        elif metric not in TESTBENCH_CHECKS:
            raise ValueError(f"unknown final_eval metric: {metric}")

    compiles = by_name["compile"].passed if "compile" in by_name else False
    golden_rtl_passed = (
        (compiles and by_name["simulate"].passed) if "simulate" in by_name else False
    )
    fp = (
        by_name["false_positive"].details.get("false_positive", False)
        if "false_positive" in by_name
        else (compiles and not golden_rtl_passed)
    )
    cov_score = (
        float(by_name["coverage"].details.get("coverage_score", 0.0))
        if ("coverage" in by_name and compiles)
        else 0.0
    )
    mut_details = by_name["mutations"].details if ("mutations" in by_name and compiles) else {}
    audit_passed = (
        by_name["assertion_audit"].passed if "assertion_audit" in by_name else True
    )

    eval_result = EvalResult(
        design=design.name,
        seed=design_run.seed,
        compiles=compiles,
        golden_rtl_passed=golden_rtl_passed,
        false_positive=fp,
        coverage_score=cov_score,
        mutants_total=int(mut_details.get("mutants_total", len(design.golden_mutants))),
        mutants_killed=int(mut_details.get("mutants_killed", 0)),
        mutation_score=float(mut_details.get("mutation_score", 0.0)),
        turns=len(design_run.iterations),
        total_tokens=design_run.total_tokens,
        total_cost_usd=design_run.total_cost_usd,
        total_wall_time_s=design_run.total_wall_time_s,
        assertion_audit_passed=audit_passed,
        killed_list=list(mut_details.get("killed_list", [])),
        survived_list=list(mut_details.get("survived_list", [])),
        checks=ordered_checks,
    )
    (final_dir / "eval.json").write_text(
        json.dumps(asdict(eval_result), indent=2) + "\n"
    )
    return eval_result
