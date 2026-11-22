"""Dispatcher: reads ExperimentConfig.feedback, calls evaluation.testbench checks,
and saves iteration check artifacts in iterations/iter_<k>/."""

from pathlib import Path
from evaluation import testbench
from framework.models import CheckResult, Design, FeedbackConfig

CHECKS = {
    "compile": testbench.check_compile,
    "simulate": testbench.check_simulate,
    "self_check": testbench.check_self_check,
    "coverage": testbench.check_coverage,
    "spec_check": testbench.check_spec_check,
}


def run_iteration_checks(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    feedback_configs: list[FeedbackConfig],
) -> list[CheckResult]:
    """Dispatch each configured feedback check to evaluation.testbench."""
    results = []
    for fb in feedback_configs:
        if fb.name not in CHECKS:
            raise ValueError(f"unknown feedback check: {fb.name}")
        results.append(CHECKS[fb.name](design, tb_path, iter_dir, fb))
    return results
