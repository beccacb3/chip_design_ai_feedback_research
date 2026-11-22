"""Dispatcher: reads ExperimentConfig.testing, runs each test in evaluation.testbench,
and saves iteration check artifacts in iterations/iter_<k>/checks.json."""

from dataclasses import asdict
import json
from pathlib import Path

from evaluation import testbench
from framework.models import CheckResult, Design, SimulationConfig, TestingConfig

CHECKS = {
    "compile": testbench.check_compile,
    "simulate": testbench.check_simulate,
    "mutations": testbench.check_mutations,
    "coverage": testbench.check_coverage,
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
        if cfg.name not in CHECKS:
            raise ValueError(f"unknown testing check: {cfg.name}")
        result = CHECKS[cfg.name](design, tb_path, iter_dir, sim, cfg)
        results.append(result)
        # If compilation failed, skip downstream runtime checks for this iteration.
        if cfg.name == "compile" and not result.passed:
            break

    (iter_dir / "checks.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2) + "\n"
    )
    return results
