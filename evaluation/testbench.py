"""Single-testbench check functions (used in E1-E4 loops and in Section 4.1 final evaluation).

Functions:
  - `check_compile`                 -- E1+ & §4.1.3: compilation results
  - `check_simulate`                -- E1+ & §4.1.3: simulation pass/fail, assertion failures, runtime errors
  - `check_requirement_groups`      -- E2+ & §4.1.6: localized pass/fail & assertion tracing per requirement group
  - `check_req_code_coverage`       -- E3+ & §4.1.5: RTL code coverage overall and per requirement group
  - `check_req_functional_coverage` -- E4+ & §4.1.7: specification coverpoint coverage per requirement group
  - `check_mutations`               -- §4.1.2: mutation kill rate on golden/mutants/
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


# --------------------------------------------------------------------- 1. compile (E1+)


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


# --------------------------------------------------------------------- 2. simulate (E1+)


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
        else f"Simulation failed on the reference RTL (assertion failure or runtime error):\n{combined}"
    )
    return CheckResult(
        name="simulate",
        passed=passed,
        summary=summary,
        details={"stdout": stdout.strip(), "stderr": stderr.strip()},
    )


# --------------------------------------------------------------------- shared probe runner


_STMT_RE = re.compile(
    r"^(\s*)(?:(else\s+if\s*\([^)]*\)|if\s*\([^)]*\)|else)\s+)?([A-Za-z_]\w*(?:\[[^\]]*\])?\s*<=?\s*[^;]+;)\s*(//.*)?$"
)
_ASSIGN_RE = re.compile(r"^\s*assign\s+([A-Za-z_]\w*(?:\[[^\]]*\])?)\s*=\s*([^;]+);")


def _run_instrumented_probes(
    design: Design,
    tb_path: Path,
    work_dir: Path,
    sim: SimulationConfig,
    timeout_s: int,
) -> tuple[bool, set[str], set[str], dict[str, str], str]:
    """Instrument golden/rtl/ with line probes (`__COV__:<file>:<line>`) and
    requirement functional coverpoint probes (`__FCOV__:<req_id>:<cp_name>`).

    Returns (ok, hit_cov_tags, hit_fcov_tags, all_line_probes, diagnostics_or_stdout).
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    line_probes: dict[str, str] = {}
    inst_sources: list[Path] = []

    req_lines = {ln for req in design.requirements for ln in req.rtl_lines}

    for idx, rtl_path in enumerate(_rtl_paths(design)):
        dst = work_dir / rtl_path.name
        out_lines = []
        end_monitors = []
        in_always = False

        for lineno, line in enumerate(rtl_path.read_text().splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("always"):
                in_always = True
            elif stripped.startswith("endmodule"):
                in_always = False

            tag = f"{rtl_path.name}:{lineno}"
            m_assign = _ASSIGN_RE.match(line)
            m_stmt = _STMT_RE.match(line) if (in_always and not m_assign) else None

            if (
                m_stmt
                and not stripped.startswith(("assign ", "parameter ", "localparam "))
                and (not req_lines or lineno in req_lines)
            ):
                indent, cond, stmt, comment = (
                    m_stmt.group(1),
                    m_stmt.group(2),
                    m_stmt.group(3),
                    m_stmt.group(4) or "",
                )
                line_probes[tag] = f"{rtl_path.name}:{lineno}: {stripped}"
                prefix = f"{cond} " if cond else ""
                out_lines.append(
                    f'{indent}{prefix}begin $display("__COV__:{tag}"); {stmt} end {comment}'.rstrip()
                )
            elif m_assign and (not req_lines or lineno in req_lines):
                lhs = m_assign.group(1)
                line_probes[tag] = f"{rtl_path.name}:{lineno}: {stripped}"
                out_lines.append(line)
                end_monitors.append(
                    f'always @({lhs}) if ({lhs} !== 1\'bx) $display("__COV__:{tag}");'
                )
            else:
                out_lines.append(line)

        # Inject requirement functional coverpoint monitors into the top module file
        if idx == 0:
            for req in design.requirements:
                for cp_name, expr in req.coverpoints.items():
                    end_monitors.append(
                        f'always @(*) if ({expr}) $display("__FCOV__:{req.id}:{cp_name}");'
                    )

        # Insert end_monitors right before `endmodule`
        final_lines = []
        inserted = False
        for line in out_lines:
            if not inserted and line.strip().startswith("endmodule"):
                final_lines.extend(end_monitors)
                inserted = True
            final_lines.append(line)
        dst.write_text("\n".join(final_lines) + "\n")
        inst_sources.append(dst)

    cov_bin = work_dir / "probe.out"
    ok, diag = compile_verilog([*inst_sources, Path(tb_path)], cov_bin, args=sim.args)
    if not ok:
        return False, set(), set(), line_probes, diag

    _, stdout, stderr = run_simulation(cov_bin, timeout_s=timeout_s)
    combined = stdout + "\n" + stderr
    hit_cov = {
        ln.split("__COV__:", 1)[1].strip()
        for ln in combined.splitlines()
        if "__COV__:" in ln
    }
    hit_fcov = {
        ln.split("__FCOV__:", 1)[1].strip()
        for ln in combined.splitlines()
        if "__FCOV__:" in ln
    }
    return True, hit_cov, hit_fcov, line_probes, combined


# --------------------------------------------------------------------- 3. E2: requirement_groups (§2.3 E2 & §4.1.6)


def check_requirement_groups(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """E2 & §4.1.6: Localized feedback by requirement groups (pass/fail & assertion failures per group)."""
    iter_dir = Path(iter_dir)
    iter_dir.mkdir(parents=True, exist_ok=True)
    timeout_s = int(cfg.options.get("timeout_s", sim.timeout_s))

    sim_log = (iter_dir / "sim.log").read_text() if (iter_dir / "sim.log").exists() else ""
    tb_text = Path(tb_path).read_text() if Path(tb_path).exists() else ""

    ok, hit_cov, hit_fcov, _, _ = _run_instrumented_probes(
        design, tb_path, iter_dir / "probe_work", sim, timeout_s
    )
    if not ok:
        return CheckResult(
            name="requirement_groups",
            passed=False,
            summary="Requirement group check could not run because compilation failed.",
        )

    hit_line_nums = {int(t.rsplit(":", 1)[1]) for t in hit_cov if ":" in t}
    fail_lines = [
        ln.strip()
        for ln in sim_log.splitlines()
        if any(k in ln.upper() for k in ("FAIL", "ERROR", "FATAL", "MISMATCH"))
    ]

    groups_report = {}
    exercised_count = 0
    passing_count = 0
    lines_for_summary = []

    for req in design.requirements:
        # A requirement group is exercised if tagged in TB/log, or if its coverpoints/lines fired
        tagged = (req.id in tb_text) or (req.id in sim_log)
        fcov_hits = [cp for cp in req.coverpoints if f"{req.id}:{cp}" in hit_fcov]
        line_hits = [ln for ln in req.rtl_lines if ln in hit_line_nums]
        exercised = tagged or bool(fcov_hits) or (
            bool(line_hits) and len(fcov_hits) == len(req.coverpoints)
        )

        group_failures = [f for f in fail_lines if req.id in f]
        group_passed = exercised and not group_failures

        if exercised:
            exercised_count += 1
        if group_passed:
            passing_count += 1

        status = "PASS" if group_passed else ("FAIL (assertion error)" if group_failures else "NOT EXERCISED")
        groups_report[req.id] = {
            "description": req.description,
            "exercised": exercised,
            "passed": group_passed,
            "assertion_failures": group_failures,
        }
        lines_for_summary.append(
            f"  - [{req.id}] ({req.description}): {status}"
            + (f" -- failures: {'; '.join(group_failures)}" if group_failures else "")
        )

    total = len(design.requirements)
    score = (exercised_count / total) if total > 0 else 1.0
    passed = passing_count == total

    report_data = {
        "total_groups": total,
        "exercised_groups": exercised_count,
        "passing_groups": passing_count,
        "req_group_coverage_score": round(score, 4),
        "groups": groups_report,
    }
    (iter_dir / "requirement_groups.json").write_text(json.dumps(report_data, indent=2) + "\n")

    summary = (
        f"Requirement groups passing: {passing_count}/{total} (exercised: {exercised_count}/{total}, {score:.0%}).\n"
        + "\n".join(lines_for_summary)
    )
    return CheckResult(
        name="requirement_groups",
        passed=passed,
        summary=summary,
        details=report_data,
    )


# --------------------------------------------------------------------- 4. E3: req_code_coverage (§2.3 E3 & §4.1.5)


def check_req_code_coverage(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """E3 & §4.1.5: RTL code coverage overall and per requirement group."""
    iter_dir = Path(iter_dir)
    iter_dir.mkdir(parents=True, exist_ok=True)
    timeout_s = int(cfg.options.get("timeout_s", sim.timeout_s))
    min_cov = float(cfg.options.get("min_coverage", 1.0))

    ok, hit_cov, _, line_probes, diag = _run_instrumented_probes(
        design, tb_path, iter_dir / "probe_work", sim, timeout_s
    )
    if not ok:
        return CheckResult(
            name="req_code_coverage",
            passed=False,
            summary=f"Code coverage compilation failed:\n{diag.strip()}",
        )

    total = len(line_probes)
    covered = len(hit_cov & set(line_probes))
    score = (covered / total) if total > 0 else 1.0
    uncovered = [desc for tag, desc in line_probes.items() if tag not in hit_cov]

    hit_line_nums = {int(t.rsplit(":", 1)[1]) for t in hit_cov if ":" in t}
    per_group = {}
    group_lines = []
    for req in design.requirements:
        r_total = len(req.rtl_lines)
        r_hit = [ln for ln in req.rtl_lines if ln in hit_line_nums]
        r_missed = [ln for ln in req.rtl_lines if ln not in hit_line_nums]
        r_score = (len(r_hit) / r_total) if r_total > 0 else 1.0
        per_group[req.id] = {
            "rtl_lines": req.rtl_lines,
            "covered_lines": r_hit,
            "uncovered_lines": r_missed,
            "coverage_score": round(r_score, 4),
        }
        group_lines.append(
            f"  - [{req.id}] code coverage: {len(r_hit)}/{r_total} ({r_score:.0%})"
            + (f" -- uncovered RTL lines: {r_missed}" if r_missed else "")
        )

    passed = score >= min_cov and all(
        g["coverage_score"] >= min_cov for g in per_group.values()
    )
    report_data = {
        "total_points": total,
        "covered_points": covered,
        "coverage_score": round(score, 4),
        "uncovered_lines": uncovered,
        "per_requirement_group": per_group,
    }
    (iter_dir / "coverage.json").write_text(json.dumps(report_data, indent=2) + "\n")

    summary = (
        f"RTL code coverage: {covered}/{total} ({score:.0%}, target {min_cov:.0%}).\n"
        + "\n".join(group_lines)
    )
    if uncovered:
        summary += "\nUncovered RTL statements:\n" + "\n".join(f"  - {u}" for u in uncovered)

    return CheckResult(
        name="req_code_coverage",
        passed=passed,
        summary=summary,
        details=report_data,
    )


# Alias for backward compatibility
check_coverage = check_req_code_coverage


# --------------------------------------------------------------------- 5. E4: req_functional_coverage (§2.3 E4 & §4.1.7)


def check_req_functional_coverage(
    design: Design,
    tb_path: Path,
    iter_dir: Path,
    sim: SimulationConfig,
    cfg: TestingConfig,
) -> CheckResult:
    """E4 & §4.1.7: Specification-derived functional coverpoint coverage per requirement group."""
    iter_dir = Path(iter_dir)
    iter_dir.mkdir(parents=True, exist_ok=True)
    timeout_s = int(cfg.options.get("timeout_s", sim.timeout_s))
    min_fcov = float(cfg.options.get("min_functional_coverage", 1.0))

    ok, _, hit_fcov, _, diag = _run_instrumented_probes(
        design, tb_path, iter_dir / "probe_work", sim, timeout_s
    )
    if not ok:
        return CheckResult(
            name="req_functional_coverage",
            passed=False,
            summary=f"Functional coverage compilation failed:\n{diag.strip()}",
        )

    all_cps = [
        f"{req.id}:{cp_name}"
        for req in design.requirements
        for cp_name in req.coverpoints
    ]
    hit_list = [cp for cp in all_cps if cp in hit_fcov]
    missed_list = [cp for cp in all_cps if cp not in hit_fcov]
    total = len(all_cps)
    score = (len(hit_list) / total) if total > 0 else 1.0

    per_group = {}
    group_lines = []
    for req in design.requirements:
        g_total = len(req.coverpoints)
        g_hit = [cp for cp in req.coverpoints if f"{req.id}:{cp}" in hit_fcov]
        g_missed = [cp for cp in req.coverpoints if f"{req.id}:{cp}" not in hit_fcov]
        g_score = (len(g_hit) / g_total) if g_total > 0 else 1.0
        per_group[req.id] = {
            "description": req.description,
            "hit_coverpoints": g_hit,
            "missed_coverpoints": g_missed,
            "functional_coverage_score": round(g_score, 4),
        }
        group_lines.append(
            f"  - [{req.id}] functional coverage: {len(g_hit)}/{g_total} ({g_score:.0%})"
            + (f" -- missed scenarios: {g_missed}" if g_missed else "")
        )

    passed = score >= min_fcov
    report_data = {
        "total_coverpoints": total,
        "hit_coverpoints_count": len(hit_list),
        "functional_coverage_score": round(score, 4),
        "hit_coverpoints": hit_list,
        "missed_coverpoints": missed_list,
        "per_requirement_group": per_group,
    }
    (iter_dir / "functional_coverage.json").write_text(json.dumps(report_data, indent=2) + "\n")

    summary = (
        f"Specification functional coverage: {len(hit_list)}/{total} ({score:.0%}, target {min_fcov:.0%}).\n"
        + "\n".join(group_lines)
    )
    return CheckResult(
        name="req_functional_coverage",
        passed=passed,
        summary=summary,
        details=report_data,
    )


# --------------------------------------------------------------------- 6. mutations (§4.1.2)


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
    """§4.1.2: Run tb_path against each file in golden/mutants/ and write mutations.json."""
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
            f"Survived mutants: {', '.join(survived)}."
        )
    return CheckResult(
        name="mutations",
        passed=passed,
        summary=summary,
        details=report_data,
    )
