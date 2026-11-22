"""Atomic testbench check functions (used both in-loop and in final evaluation).

Each function:
  1. Takes (design, tb_path, iter_dir, sim, cfg).
  2. Writes its log or JSON output into `iter_dir`.
  3. Returns a `CheckResult(name, passed, summary, details)`.
"""

import json
import re
from pathlib import Path

from designs.standardize import module_names
from evaluation.simulation import compile_verilog, run_simulation
from framework.models import CheckResult, Design, SimulationConfig, TestingConfig

REPO_ROOT = Path(__file__).resolve().parent.parent


def _rtl_paths(design: Design) -> list[Path]:
    return [REPO_ROOT / p for p in design.golden_rtl]


# --------------------------------------------------------------------- 1. compile


def check_compile(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """Compile tb_path with golden/rtl/ using iverilog and write compile.log."""
    iter_dir = Path(iter_dir)
    iter_dir.mkdir(parents=True, exist_ok=True)
    sim_bin = iter_dir / "sim.out"

    ok, diagnostics = compile_verilog(
        [*_rtl_paths(design), Path(tb_path)],
        sim_bin,
        args=sim.args,
    )
    (iter_dir / "compile.log").write_text(diagnostics)

    summary = (
        "Compilation succeeded."
        if ok
        else f"Compilation failed:\n{diagnostics.strip()}"
    )
    return CheckResult(
        name="compile",
        passed=ok,
        summary=summary,
        details={"binary": str(sim_bin), "diagnostics": diagnostics.strip()},
    )


# --------------------------------------------------------------------- 2. simulate


def check_simulate(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """Run the compiled testbench against golden/rtl/ and write sim.log."""
    iter_dir = Path(iter_dir)
    iter_dir.mkdir(parents=True, exist_ok=True)
    sim_bin = iter_dir / "sim.out"

    if not sim_bin.exists():
        comp = check_compile(design, tb_path, iter_dir, sim, cfg)
        if not comp.passed:
            return CheckResult(
                name="simulate",
                passed=False,
                summary=f"Cannot simulate because compilation failed:\n{comp.summary}",
            )

    timeout_s = int(cfg.options.get("timeout_s", sim.timeout_s))
    passed, stdout, stderr = run_simulation(sim_bin, timeout_s=timeout_s)
    combined = (stdout + ("\n" + stderr if stderr else "")).strip()
    (iter_dir / "sim.log").write_text(combined + "\n")

    summary = (
        "Simulation passed on the reference RTL."
        if passed
        else f"Simulation failed on the reference RTL (testbench rejected the valid design or timed out):\n{combined}"
    )
    return CheckResult(
        name="simulate",
        passed=passed,
        summary=summary,
        details={"stdout": stdout.strip(), "stderr": stderr.strip()},
    )


# --------------------------------------------------------------------- 3. mutations


def _sources_for_mutant(design: Design, mutant_path: Path) -> list[Path]:
    """Replace the matching module in golden_rtl with mutant_path."""
    rtl_files = _rtl_paths(design)
    if len(rtl_files) <= 1:
        return [mutant_path]
    mutant_mods = set(module_names(mutant_path))
    return [
        mutant_path if (set(module_names(f)) & mutant_mods) else f
        for f in rtl_files
    ]


def check_mutations(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """Run tb_path against each file in golden/mutants/ and write mutations.json."""
    iter_dir = Path(iter_dir)
    iter_dir.mkdir(parents=True, exist_ok=True)
    mutants_dir = iter_dir / "mutants_work"
    mutants_dir.mkdir(exist_ok=True)

    timeout_s = int(cfg.options.get("timeout_s", sim.timeout_s))
    min_kill_rate = float(cfg.options.get("min_kill_rate", 1.0))

    killed, survived = [], []
    for rel_mutant in design.golden_mutants:
        mutant_path = REPO_ROOT / rel_mutant
        name = mutant_path.name
        out_bin = mutants_dir / f"{mutant_path.stem}.out"
        sources = [*_sources_for_mutant(design, mutant_path), Path(tb_path)]

        ok, _ = compile_verilog(sources, out_bin, args=sim.args)
        if not ok:
            survived.append(name)
            continue

        sim_passed, _, _ = run_simulation(out_bin, timeout_s=timeout_s)
        # A mutant is killed when the testbench detects the bug (simulation fails).
        if not sim_passed:
            killed.append(name)
        else:
            survived.append(name)

    total = len(design.golden_mutants)
    score = (len(killed) / total) if total > 0 else 1.0
    passed = score >= min_kill_rate

    report_data = {
        "mutants_total": total,
        "mutants_killed": len(killed),
        "mutation_score": round(score, 4),
        "killed_list": killed,
        "survived_list": survived,
    }
    (iter_dir / "mutations.json").write_text(json.dumps(report_data, indent=2) + "\n")

    if passed:
        summary = f"Killed {len(killed)}/{total} mutants ({score:.0%})."
    else:
        summary = (
            f"Killed {len(killed)}/{total} mutants ({score:.0%}, target {min_kill_rate:.0%}). "
            f"The testbench did not catch these buggy RTL variants: {', '.join(survived)}."
        )
    return CheckResult(
        name="mutations",
        passed=passed,
        summary=summary,
        details=report_data,
    )


# --------------------------------------------------------------------- 4. coverage


_STMT_RE = re.compile(
    r"^(\s*)(?:(else\s+if\s*\([^)]*\)|if\s*\([^)]*\)|else)\s+)?([A-Za-z_]\w*(?:\[[^\]]*\])?\s*<=?\s*[^;]+;)\s*(//.*)?$"
)


def _instrument_rtl(rtl_path: Path, dst_path: Path) -> dict[str, str]:
    """Insert $display coverage probes on procedural assignment lines inside always blocks."""
    probes: dict[str, str] = {}
    out_lines = []
    in_always = False

    for lineno, line in enumerate(rtl_path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("always"):
            in_always = True
        elif stripped.startswith("endmodule"):
            in_always = False

        m = _STMT_RE.match(line) if in_always else None
        if m and not stripped.startswith(("assign ", "parameter ", "localparam ")):
            indent, cond, stmt, comment = m.group(1), m.group(2), m.group(3), m.group(4) or ""
            tag = f"{rtl_path.name}:{lineno}"
            probes[tag] = f"{rtl_path.name}:{lineno}: {stripped}"
            prefix = f"{cond} " if cond else ""
            out_lines.append(
                f'{indent}{prefix}begin $display("__COV__:{tag}"); {stmt} end {comment}'.rstrip()
            )
        else:
            out_lines.append(line)

    dst_path.write_text("\n".join(out_lines) + "\n")
    return probes


def check_coverage(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """Measure procedural statement/branch coverage on golden/rtl/ and write coverage.json."""
    iter_dir = Path(iter_dir)
    iter_dir.mkdir(parents=True, exist_ok=True)
    cov_dir = iter_dir / "coverage_work"
    cov_dir.mkdir(exist_ok=True)

    probes: dict[str, str] = {}
    inst_sources: list[Path] = []
    for rtl_path in _rtl_paths(design):
        dst = cov_dir / rtl_path.name
        probes.update(_instrument_rtl(rtl_path, dst))
        inst_sources.append(dst)

    cov_bin = cov_dir / "cov.out"
    ok, diag = compile_verilog([*inst_sources, Path(tb_path)], cov_bin, args=sim.args)
    if not ok:
        return CheckResult(
            name="coverage",
            passed=False,
            summary=f"Coverage compilation failed:\n{diag.strip()}",
        )

    timeout_s = int(cfg.options.get("timeout_s", sim.timeout_s))
    _, stdout, _ = run_simulation(cov_bin, timeout_s=timeout_s)

    hit_tags = {
        line.split("__COV__:", 1)[1].strip()
        for line in stdout.splitlines()
        if "__COV__:" in line
    }
    total = len(probes)
    covered = len(hit_tags & set(probes))
    score = (covered / total) if total > 0 else 1.0
    min_cov = float(cfg.options.get("min_coverage", 0.90))
    passed = score >= min_cov

    uncovered = [desc for tag, desc in probes.items() if tag not in hit_tags]
    report_data = {
        "total_points": total,
        "covered_points": covered,
        "coverage_score": round(score, 4),
        "uncovered_lines": uncovered,
    }
    (iter_dir / "coverage.json").write_text(json.dumps(report_data, indent=2) + "\n")

    if passed:
        summary = f"RTL statement coverage: {covered}/{total} ({score:.0%})."
    else:
        uncovered_str = "\n".join(f"  - {u}" for u in uncovered)
        summary = (
            f"RTL statement coverage is {covered}/{total} ({score:.0%}, target {min_cov:.0%}).\n"
            f"Uncovered RTL statements:\n{uncovered_str}"
        )
    return CheckResult(
        name="coverage",
        passed=passed,
        summary=summary,
        details=report_data,
    )
