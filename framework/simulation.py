
"""Compile and run Verilog testbenches using Icarus Verilog."""

import subprocess
from pathlib import Path


def compile_verilog(
    sources: list[Path],
    out_bin: Path,
    args: list[str] | None = None,
) -> tuple[bool, str]:
    """Compile Verilog sources. Returns (success, diagnostics)."""

    if not sources:
        return False, "No Verilog source files provided."

    out_bin = Path(out_bin)
    out_bin.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "iverilog",
        "-g2012",
        *(args or []),
        "-o",
        str(out_bin),
        *(str(source) for source in sources),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError:
        return False, "iverilog is not installed."
    except subprocess.TimeoutExpired:
        return False, "Compilation timed out."

    diagnostics = result.stdout + result.stderr
    return result.returncode == 0, diagnostics


def run_simulation(
    sim_bin: Path,
    timeout_s: int = 10,
) -> tuple[bool, str, str]:
    """Run a compiled simulation. Returns (success, stdout, stderr)."""

    try:
        result = subprocess.run(
            ["vvp", str(sim_bin)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        return False, "", "vvp is not installed."
    except subprocess.TimeoutExpired:
        return False, "", "Simulation timed out."

    return (
        result.returncode == 0,
        result.stdout,
        result.stderr,
    )
