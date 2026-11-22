
"""Reusable testbench checks (used both during iterations and in final evaluation)."""

from pathlib import Path

from framework.models import CheckResult, Design, SimulationConfig, TestingConfig
from evaluation.simulation import compile_verilog, run_simulation


def check_compile(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """Compile tb_path with golden RTL."""

    if sim.tool != "iverilog":
        return CheckResult(
            name=cfg.name,
            passed=False,
            summary=f"Unsupported simulator: {sim.tool}",
        )

    output_bin = Path(iter_dir) / "simulation.out"
    sources = [Path(p) for p in design.golden_rtl] + [Path(tb_path)]

    success, diagnostics = compile_verilog(
        sources=sources,
        out_bin=output_bin,
        args=sim.args,
    )

    return CheckResult(
        name=cfg.name,
        passed=success,
        summary="Compilation passed." if success else f"Compilation failed:\n{diagnostics}",
        details={
            "output_bin": str(output_bin),
            "diagnostics": diagnostics,
        },
    )


def check_simulate(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """Compile and run a testbench against golden RTL."""

    compile_result = check_compile(
        design=design,
        tb_path=tb_path,
        iter_dir=iter_dir,
        sim=sim,
        cfg=TestingConfig(name="compile"),
    )

    if not compile_result.passed:
        return CheckResult(
            name=cfg.name,
            passed=False,
            summary=compile_result.summary,
            details=compile_result.details,
        )

    output_bin = Path(compile_result.details["output_bin"])

    passed, stdout, stderr = run_simulation(
        sim_bin=output_bin,
        timeout_s=sim.timeout_s,
    )

    return CheckResult(
        name=cfg.name,
        passed=passed,
        summary="Simulation passed." if passed else f"Simulation failed:\n{stdout}\n{stderr}",
        details={
            "stdout": stdout,
            "stderr": stderr,
        },
    )


def check_self_check(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """CorrectBench-style check against candidate RTL implementations."""
    raise NotImplementedError


def check_coverage(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """Spec2Cov-style code coverage check using verilator."""
    raise NotImplementedError


def check_spec_check(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """LLM-as-judge check that every requirement in spec.md is tested."""
    raise NotImplementedError
