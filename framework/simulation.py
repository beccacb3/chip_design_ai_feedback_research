"""3. Simulation wrapper: compiles and runs Verilog with iverilog / vvp / verilator."""

from pathlib import Path


def compile_verilog(sources: list[Path], out_bin: Path, args: list[str] | None = None) -> tuple[bool, str]:
    """Compile Verilog sources with iverilog. Returns (success, stderr)."""
    raise NotImplementedError


def run_simulation(sim_bin: Path, timeout_s: int = 10) -> tuple[bool, str, str]:
    """Run a compiled simulation binary with vvp. Returns (passed, stdout, stderr)."""
    raise NotImplementedError
