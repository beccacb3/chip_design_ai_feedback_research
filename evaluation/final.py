"""Final-only evaluation functions (Section 4.1 of the Research Ideation Report).

While `evaluation/testbench.py` defines single-testbench checks (`compile`,
`simulate`, `requirement_groups`, `req_code_coverage`, `req_functional_coverage`,
`mutations`), this module defines the final-only evaluations that compare against
the reference golden testbench or summarize the full refinement trajectory:

  - `eval_golden_tb_comparison` -- §4.1.1 FixMe Golden Testbenches comparison
  - `eval_golden_rtl_acceptance` -- §4.1.3 Golden RTL Acceptance (no false positives)
  - `eval_computational_cost`   -- §4.1.4 Computational Cost (tokens, iterations, API calls, sim time)
"""

from pathlib import Path

from evaluation.testbench import (
    REPO_ROOT,
    check_req_code_coverage,
    check_req_functional_coverage,
)
from framework.models import (
    CheckResult,
    Design,
    DesignRun,
    SimulationConfig,
    TestingConfig,
)


def eval_golden_tb_comparison(
    design: Design,
    design_run: DesignRun,
    design_run_dir: Path,
    sim: SimulationConfig,
    prior_results: dict[str, CheckResult],
) -> CheckResult:
    """§4.1.1: Compare generated TB against FixMe golden TB on code & functional coverage."""
    gen_cov = prior_results.get("req_code_coverage")
    gen_fcov = prior_results.get("req_functional_coverage")
    gen_cov_score = float(gen_cov.details.get("coverage_score", 0.0)) if gen_cov else 0.0
    gen_hit_cps = set(gen_fcov.details.get("hit_coverpoints", [])) if gen_fcov else set()
    gen_fcov_score = float(gen_fcov.details.get("functional_coverage_score", 0.0)) if gen_fcov else 0.0

    if not design.golden_tb:
        return CheckResult(
            name="golden_tb_comparison",
            passed=True,
            summary="No reference golden testbench present for comparison.",
            details={
                "golden_code_coverage": 0.0,
                "generated_code_coverage": gen_cov_score,
                "golden_functional_coverage": 0.0,
                "generated_functional_coverage": gen_fcov_score,
                "missed_scenarios_vs_golden": [],
                "extra_scenarios_over_golden": sorted(gen_hit_cps),
            },
        )

    golden_tb_path = REPO_ROOT / design.golden_tb[0]
    work_dir = Path(design_run_dir) / "final" / "golden_tb_work"
    g_cov = check_req_code_coverage(
        design, golden_tb_path, work_dir, sim, TestingConfig(name="req_code_coverage")
    )
    g_fcov = check_req_functional_coverage(
        design, golden_tb_path, work_dir, sim, TestingConfig(name="req_functional_coverage")
    )

    g_cov_score = float(g_cov.details.get("coverage_score", 0.0))
    g_hit_cps = set(g_fcov.details.get("hit_coverpoints", []))
    g_fcov_score = float(g_fcov.details.get("functional_coverage_score", 0.0))

    missed_vs_golden = sorted(g_hit_cps - gen_hit_cps)
    extra_over_golden = sorted(gen_hit_cps - g_hit_cps)
    passed = len(missed_vs_golden) == 0

    summary = (
        f"vs. Golden TB: code_cov={gen_cov_score:.0%} (golden {g_cov_score:.0%}), "
        f"func_cov={gen_fcov_score:.0%} (golden {g_fcov_score:.0%}), "
        f"missed_vs_golden={missed_vs_golden}, extra_over_golden={extra_over_golden}."
    )
    return CheckResult(
        name="golden_tb_comparison",
        passed=passed,
        summary=summary,
        details={
            "golden_code_coverage": g_cov_score,
            "generated_code_coverage": gen_cov_score,
            "golden_functional_coverage": g_fcov_score,
            "generated_functional_coverage": gen_fcov_score,
            "missed_scenarios_vs_golden": missed_vs_golden,
            "extra_scenarios_over_golden": extra_over_golden,
        },
    )


def eval_golden_rtl_acceptance(
    design: Design,
    design_run: DesignRun,
    design_run_dir: Path,
    sim: SimulationConfig,
    prior_results: dict[str, CheckResult],
) -> CheckResult:
    """§4.1.3: Verify the generated testbench accepts the valid golden RTL without false alarms."""
    comp = prior_results.get("compile")
    sim_res = prior_results.get("simulate")
    compiled = comp.passed if comp else False
    sim_passed = sim_res.passed if sim_res else False

    accepted = bool(compiled and sim_passed)
    false_positive = bool(compiled and not sim_passed)
    summary = (
        "Accepted golden RTL without false-positive failures."
        if accepted
        else (
            "False positive: compiled testbench rejected the valid golden RTL."
            if false_positive
            else "Failed to compile against golden RTL."
        )
    )
    return CheckResult(
        name="golden_rtl_acceptance",
        passed=accepted,
        summary=summary,
        details={
            "accepted": accepted,
            "false_positive": false_positive,
        },
    )


def eval_computational_cost(
    design: Design,
    design_run: DesignRun,
    design_run_dir: Path,
    sim: SimulationConfig,
    prior_results: dict[str, CheckResult],
) -> CheckResult:
    """§4.1.4: Record LLM tokens, iterations, LLM API calls, cost ($), and simulation execution time."""
    turns = len(design_run.iterations)
    summary = (
        f"Iterations={turns}, LLM calls={design_run.num_llm_calls}, "
        f"tokens={design_run.total_tokens}, cost=${design_run.total_cost_usd:.6f}, "
        f"llm_time={design_run.llm_wall_time_s:.2f}s, sim_time={design_run.sim_wall_time_s:.2f}s."
    )
    return CheckResult(
        name="computational_cost",
        passed=True,
        summary=summary,
        details={
            "turns": turns,
            "num_llm_calls": design_run.num_llm_calls,
            "total_tokens": design_run.total_tokens,
            "total_cost_usd": design_run.total_cost_usd,
            "llm_wall_time_s": design_run.llm_wall_time_s,
            "sim_wall_time_s": design_run.sim_wall_time_s,
        },
    )
