"""Dispatcher: reads ExperimentConfig.testing, calls evaluation.testbench checks,
and saves iteration check artifacts in iterations/iter_<k>/."""

from pathlib import Path
from evaluation import testbench
from framework.models import CheckResult, Design, SimulationConfig, TestingConfig

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
    sim: SimulationConfig,
    testing_configs: list[TestingConfig],
) -> list[CheckResult]:
    """Dispatch each configured test in `testing` to evaluation.testbench."""
    results = []
    for cfg in testing_configs:
        if cfg.name not in CHECKS:
            raise ValueError(f"unknown testing check: {cfg.name}")
        results.append(CHECKS[cfg.name](design, tb_path, iter_dir, sim, cfg))
    return results
