"""Simulation runner: invokes iverilog, vvp, or verilator and writes sim.log."""

from pathlib import Path


def compile_verilog(sources: list[Path], out_bin: Path, args: list[str] | None = None) -> tuple[bool, str]:
    """Compile Verilog sources with iverilog. Returns (success, stderr)."""
    raise NotImplementedError


def run_simulation(sim_bin: Path, timeout_s: int = 10) -> tuple[bool, str, str]:
    """Run a compiled simulation binary with vvp. Returns (passed, stdout, stderr)."""
    raise NotImplementedError


def run_verilator_coverage(sources: list[Path], work_dir: Path, args: list[str] | None = None) -> dict:
    """Run verilator coverage and return coverage metrics."""
    raise NotImplementedError
