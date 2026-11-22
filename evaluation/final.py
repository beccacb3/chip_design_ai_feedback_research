"""Final-only evaluation functions (trajectory and audit metrics from the report).

Just as `evaluation/testbench.py` defines single-testbench checks (`compile`,
`simulate`, `coverage`, `mutations`) that can run in-loop or at the end, this
module defines evaluations that only apply in the final stage after the agent
loop finishes:

  - `eval_false_positive`  -- False Positive Rate (FPR) on Golden RTL
  - `eval_turns`           -- Multi-Turn Feedback Cycles (Turns)
  - `eval_cost_and_time`   -- Token / Compute Cost Overhead
  - `eval_assertion_audit` -- Assertion Gaming / Deletion Audit
"""

import re
from pathlib import Path

from framework.models import CheckResult, DesignRun

ASSERTION_RE = re.compile(
    r"(\$fatal\b|\$error\b|\bassert\b|!==|!=)",
    re.MULTILINE,
)


def count_assertions(tb_path: Path) -> int:
    """Count check/assertion constructs in a Verilog testbench."""
    if not tb_path.is_file():
        return 0
    return len(ASSERTION_RE.findall(tb_path.read_text()))


def eval_false_positive(
    design_run: DesignRun,
    design_run_dir: Path,
    prior_results: dict[str, CheckResult],
) -> CheckResult:
    """Check if the final testbench compiled but falsely rejected the golden RTL."""
    comp = prior_results.get("compile")
    sim = prior_results.get("simulate")
    compiled = comp.passed if comp else False
    sim_passed = sim.passed if sim else False

    is_fp = bool(compiled and not sim_passed)
    passed = not is_fp
    summary = (
        "No false positive on golden RTL."
        if passed
        else "False positive: testbench compiled but rejected the known-good golden RTL."
    )
    return CheckResult(
        name="false_positive",
        passed=passed,
        summary=summary,
        details={"false_positive": is_fp},
    )


def eval_turns(
    design_run: DesignRun,
    design_run_dir: Path,
    prior_results: dict[str, CheckResult],
) -> CheckResult:
    """Record the number of iterations (turns) used and whether the loop converged."""
    turns = len(design_run.iterations)
    converged = design_run.final_passed
    summary = f"Used {turns} iteration(s); converged={converged}."
    return CheckResult(
        name="turns",
        passed=converged,
        summary=summary,
        details={"turns": turns, "converged": converged},
    )


def eval_cost_and_time(
    design_run: DesignRun,
    design_run_dir: Path,
    prior_results: dict[str, CheckResult],
) -> CheckResult:
    """Record total tokens, USD cost, and wall-clock time across all iterations."""
    summary = (
        f"Tokens={design_run.total_tokens}, "
        f"cost=${design_run.total_cost_usd:.6f}, "
        f"time={design_run.total_wall_time_s:.2f}s."
    )
    return CheckResult(
        name="cost_and_time",
        passed=True,
        summary=summary,
        details={
            "total_tokens": design_run.total_tokens,
            "total_cost_usd": design_run.total_cost_usd,
            "total_wall_time_s": design_run.total_wall_time_s,
        },
    )


def eval_assertion_audit(
    design_run: DesignRun,
    design_run_dir: Path,
    prior_results: dict[str, CheckResult],
) -> CheckResult:
    """Audit iter_0 vs. final testbench for assertion deletion or vacuous pass."""
    design_run_dir = Path(design_run_dir)
    iter0_tb = design_run_dir / "iterations" / "iter_0" / "testbench.sv"
    final_tb = design_run_dir / design_run.final_testbench

    iter0_count = count_assertions(iter0_tb)
    final_count = count_assertions(final_tb)
    deleted = max(0, iter0_count - final_count)
    vacuous = final_count == 0

    mut = prior_results.get("mutations")
    killed_all = mut.passed if mut else False

    # Flag if the final TB has zero checks, or if it deleted checks without killing all mutants.
    gaming_detected = vacuous or (deleted > 0 and not killed_all)
    passed = not gaming_detected

    if passed:
        summary = f"Assertion audit passed (iter_0={iter0_count}, final={final_count})."
    else:
        summary = (
            f"Assertion gaming/vacuity flagged: iter_0 had {iter0_count} check(s), "
            f"final has {final_count} check(s) (deleted={deleted}, vacuous={vacuous})."
        )
    return CheckResult(
        name="assertion_audit",
        passed=passed,
        summary=summary,
        details={
            "iter0_checks": iter0_count,
            "final_checks": final_count,
            "deleted_checks": deleted,
            "vacuous": vacuous,
        },
    )
