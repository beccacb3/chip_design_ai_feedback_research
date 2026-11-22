"""Test & evaluation composer:
  1. `run_iteration_checks` composes `config.testing` (from `evaluation.testbench`)
     for each iteration `iterations/iter_<k>/` in E1-E4.
  2. `run_final_evaluations` composes `config.final_eval.metrics` (Section 4.1.1-4.1.7)
     using single-testbench checks (`evaluation.testbench`) and final-only
     evaluations (`evaluation.final`) for `final/eval.json`.
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
    "requirement_groups": testbench.check_requirement_groups,
    "requirement_group_coverage": testbench.check_requirement_groups,
    "req_code_coverage": testbench.check_req_code_coverage,
    "code_coverage": testbench.check_req_code_coverage,
    "coverage": testbench.check_req_code_coverage,
    "req_functional_coverage": testbench.check_req_functional_coverage,
    "functional_coverage": testbench.check_req_functional_coverage,
    "mutations": testbench.check_mutations,
    "mutation_testing": testbench.check_mutations,
}

FINAL_ONLY_EVALS = {
    "golden_tb_comparison": final_evals.eval_golden_tb_comparison,
    "golden_rtl_acceptance": final_evals.eval_golden_rtl_acceptance,
    "computational_cost": final_evals.eval_computational_cost,
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
    """Compose Section 4.1.1-4.1.7 evaluations on `final/testbench.sv` -> `final/eval.json`."""
    design_run_dir = Path(design_run_dir)
    final_dir = design_run_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_tb = design_run_dir / design_run.final_testbench

    by_name: dict[str, CheckResult] = {}
    ordered_checks: list[CheckResult] = []

    # Always run compile + simulate first so 4.1.3 golden_rtl_acceptance has them
    for base_check in ("compile", "simulate"):
        res = TESTBENCH_CHECKS[base_check](
            design, final_tb, final_dir, sim, TestingConfig(name=base_check)
        )
        by_name[base_check] = res
        if base_check in final_cfg.metrics:
            ordered_checks.append(res)

    # 1. Run all single-testbench checks requested in final_cfg.metrics
    for metric in final_cfg.metrics:
        if metric in ("compile", "simulate"):
            continue
        if metric in TESTBENCH_CHECKS:
            res = TESTBENCH_CHECKS[metric](
                design, final_tb, final_dir, sim, TestingConfig(name=metric)
            )
            by_name[metric] = res
            by_name[res.name] = res
            ordered_checks.append(res)

    # 2. Run all final-only evaluations requested in final_cfg.metrics
    for metric in final_cfg.metrics:
        if metric in FINAL_ONLY_EVALS:
            res = FINAL_ONLY_EVALS[metric](
                design, design_run, design_run_dir, sim, by_name
            )
            by_name[metric] = res
            ordered_checks.append(res)
        elif metric not in TESTBENCH_CHECKS:
            raise ValueError(f"unknown final_eval metric: {metric}")

    compiles = by_name["compile"].passed
    golden_rtl_passed = compiles and by_name["simulate"].passed
    fp = bool(compiles and not golden_rtl_passed)

    cov_res = by_name.get("req_code_coverage") or by_name.get("code_coverage")
    cov_score = float(cov_res.details.get("coverage_score", 0.0)) if (cov_res and compiles) else 0.0

    req_res = by_name.get("requirement_groups") or by_name.get("requirement_group_coverage")
    req_score = float(req_res.details.get("req_group_coverage_score", 0.0)) if (req_res and compiles) else 0.0

    fcov_res = by_name.get("req_functional_coverage") or by_name.get("functional_coverage")
    fcov_score = float(fcov_res.details.get("functional_coverage_score", 0.0)) if (fcov_res and compiles) else 0.0

    # A testbench that fails on the valid golden RTL (Eval1) cannot validly kill mutants (Eval2)
    mut_res = by_name.get("mutations") or by_name.get("mutation_testing")
    mut_details = mut_res.details if (mut_res and golden_rtl_passed) else {}

    gtb_res = by_name.get("golden_tb_comparison")
    gtb_details = gtb_res.details if gtb_res else {}

    eval_result = EvalResult(
        design=design.name,
        seed=design_run.seed,
        compiles=compiles,
        golden_rtl_passed=golden_rtl_passed,
        false_positive=fp,
        mutants_total=int(mut_details.get("mutants_total", len(design.golden_mutants))),
        mutants_killed=int(mut_details.get("mutants_killed", 0)),
        mutation_score=float(mut_details.get("mutation_score", 0.0)),
        code_coverage_score=cov_score,
        req_group_coverage_score=req_score,
        functional_coverage_score=fcov_score,
        golden_tb_functional_coverage=float(gtb_details.get("golden_functional_coverage", 0.0)),
        missed_scenarios_vs_golden=list(gtb_details.get("missed_scenarios_vs_golden", [])),
        extra_scenarios_over_golden=list(gtb_details.get("extra_scenarios_over_golden", [])),
        turns=len(design_run.iterations),
        num_llm_calls=design_run.num_llm_calls,
        total_tokens=design_run.total_tokens,
        total_cost_usd=design_run.total_cost_usd,
        llm_wall_time_s=design_run.llm_wall_time_s,
        sim_wall_time_s=design_run.sim_wall_time_s,
        killed_list=list(mut_details.get("killed_list", [])),
        survived_list=list(mut_details.get("survived_list", [])),
        checks=ordered_checks,
    )
    (final_dir / "eval.json").write_text(
        json.dumps(asdict(eval_result), indent=2) + "\n"
    )
    return eval_result
