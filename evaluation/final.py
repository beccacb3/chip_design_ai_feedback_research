
"""Final evaluation of generated testbenches against golden RTL and mutants."""

from designs.standardize import load_design

import json
import re
from dataclasses import asdict
from pathlib import Path

from evaluation.simulation import compile_verilog, run_simulation
from framework.models import Design, EvalResult


def _run_testbench(rtl_sources: list[Path], tb_path: Path, out_bin: Path):
    """Compile and simulate one RTL implementation with a testbench."""
    compiled, diagnostics = compile_verilog(
        sources=rtl_sources + [tb_path],
        out_bin=out_bin,
    )

    if not compiled:
        return False, False, diagnostics

    passed, stdout, stderr = run_simulation(out_bin)
    return True, passed, stdout + stderr


def evaluate_design_run(design: Design, design_run_dir: Path) -> EvalResult:
    """Evaluate final/testbench.sv against golden RTL and mutants."""

    design_run_dir = Path(design_run_dir)
    final_dir = design_run_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    tb_path = final_dir / "testbench.sv"

    if not tb_path.is_file():
        raise FileNotFoundError(f"Missing final testbench: {tb_path}")

    golden_sources = [Path(p) for p in design.golden_rtl]

    compiled, golden_passed, golden_output = _run_testbench(
        golden_sources,
        tb_path,
        final_dir / "golden.out",
    )

    killed = []
    survived = []
    invalid_mutants = []

    # Mutant evaluation is meaningful only when the golden RTL passes.
    if compiled and golden_passed:
        for mutant_path in design.golden_mutants:
            mutant = Path(mutant_path)

            # Replace the golden RTL file defining the same module.
            # Other golden RTL dependencies remain included.
            module_pattern = re.compile(
                rf"\bmodule\s+{re.escape(design.top_module)}\b"
            )

            remaining_sources = [
                source for source in golden_sources
                if not module_pattern.search(source.read_text())
            ]

            mutant_compiled, mutant_passed, output = _run_testbench(
                remaining_sources + [mutant],
                tb_path,
                final_dir / f"{mutant.stem}.out",
            )

            if not mutant_compiled:
                invalid_mutants.append(mutant.name)
            elif not mutant_passed:
                killed.append(mutant.name)
            else:
                survived.append(mutant.name)

    mutants_total = len(design.golden_mutants)

    mutation_score = (
        len(killed) / mutants_total
        if compiled and golden_passed and mutants_total
        else 0.0
    )

    seed_match = re.search(r"__seed(\d+)$", design_run_dir.name)
    seed = int(seed_match.group(1)) if seed_match else 0

    result = EvalResult(
        design=design.name,
        seed=seed,
        compiles=compiled,
        golden_rtl_passed=compiled and golden_passed,
        mutants_total=mutants_total,
        mutants_killed=len(killed),
        mutation_score=mutation_score,
        killed_list=killed,
        survived_list=survived,
    )

    data = asdict(result)
    data["golden_output"] = golden_output
    data["invalid_mutants"] = invalid_mutants

    (final_dir / "eval.json").write_text(
        json.dumps(data, indent=2)
    )

    return result



def evaluate_experiment_run(run_root: Path) -> dict:
    """Evaluate all design/seed folders and save summary.json."""

    run_root = Path(run_root)

    if not run_root.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_root}")

    results = []
    skipped = []

    for run_dir in sorted(run_root.iterdir()):
        if not run_dir.is_dir() or "__seed" not in run_dir.name:
            continue

        tb_path = run_dir / "final" / "testbench.sv"

        if not tb_path.is_file():
            skipped.append({
                "run": run_dir.name,
                "reason": "Missing final/testbench.sv",
            })
            continue

        design_name = run_dir.name.rsplit("__seed", 1)[0]

        matches = [
            p for p in Path("designs").glob("*/*")
            if p.is_dir() and p.name == design_name
        ]

        if len(matches) != 1:
            skipped.append({
                "run": run_dir.name,
                "reason": f"Expected one design match, found {len(matches)}",
            })
            continue

        design = load_design(matches[0])
        result = evaluate_design_run(design, run_dir)
        results.append(asdict(result))

    total = len(results)
    golden_passed = sum(r["golden_rtl_passed"] for r in results)
    mutants_total = sum(r["mutants_total"] for r in results)
    mutants_killed = sum(r["mutants_killed"] for r in results)

    summary = {
        "runs_evaluated": total,
        "runs_skipped": len(skipped),
        "compile_pass_rate": (
            sum(r["compiles"] for r in results) / total
            if total else 0.0
        ),
        "golden_rtl_pass_rate": (
            golden_passed / total if total else 0.0
        ),
        "mutation_kill_rate": (
            mutants_killed / mutants_total
            if mutants_total else 0.0
        ),
        "mutants_killed": mutants_killed,
        "mutants_total": mutants_total,
        "results": results,
        "skipped": skipped,
    }

    (run_root / "summary.json").write_text(
        json.dumps(summary, indent=2)
    )

    return summary