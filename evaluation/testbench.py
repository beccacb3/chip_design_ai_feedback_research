"""Reusable testbench checks (used both during iterations and in final evaluation)."""

from pathlib import Path
from framework.models import CheckResult, Design, SimulationConfig, TestingConfig


def check_compile(design: Design, tb_path: Path, iter_dir: Path, sim: SimulationConfig, cfg: TestingConfig) -> CheckResult:
    """Compile tb_path with golden/rtl/ using sim.tool."""
    raise NotImplementedError


def check_simulate(design: Design, tb_path: Path, iter_dir: Path, sim: SimulationConfig, cfg: TestingConfig) -> CheckResult:
    """Run compiled testbench and verify simulation completes before timeout."""
    raise NotImplementedError


def check_self_check(design: Design, tb_path: Path, iter_dir: Path, sim: SimulationConfig, cfg: TestingConfig) -> CheckResult:
    """CorrectBench-style check against candidate RTL implementations."""
    raise NotImplementedError


def check_coverage(design: Design, tb_path: Path, iter_dir: Path, sim: SimulationConfig, cfg: TestingConfig) -> CheckResult:
    """Spec2Cov-style code coverage check using verilator."""
    raise NotImplementedError


def check_spec_check(design: Design, tb_path: Path, iter_dir: Path, sim: SimulationConfig, cfg: TestingConfig) -> CheckResult:
    """LLM-as-judge check that every requirement in spec.md is tested."""
    raise NotImplementedError
