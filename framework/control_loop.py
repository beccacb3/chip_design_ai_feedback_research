"""Control flow loop: orchestrates the E1-E4 iteration loop and the Section 4.1 final evaluation stage.

Entry point for `make run`:
    python3 -m framework.control_loop configs/experiments/e1_monolithic.yaml

Entry point for `make eval` (re-runs only the final evaluation stage on a saved run):
    python3 -m framework.control_loop --eval-only runs/<experiment>/<timestamp>_<git_sha>
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Callable

import yaml

from designs.standardize import load_design
from framework.config import REPO_ROOT, load_experiment
from framework.feedback import (
    build_generate_prompt,
    build_repair_prompts,
    ensure_requirements,
    format_feedback,
    format_requirement_feedback,
    is_requirement_passing,
)
from framework.llm import call_llm, extract_code_block
from framework.models import (
    CheckResult,
    Design,
    DesignRun,
    EvalResult,
    ExperimentConfig,
    FinalEvalConfig,
    Iteration,
    LLMCall,
    Provenance,
    SimulationConfig,
)
from framework.testing import run_final_evaluations, run_iteration_checks


def _cmd_output(cmd: list[str], default: str = "unknown") -> str:
    try:
        res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=5)
        return res.stdout.strip().splitlines()[0] if res.returncode == 0 and res.stdout.strip() else default
    except Exception:
        return default


def collect_provenance(timestamp: str) -> Provenance:
    """Record git commit, dirty state, and simulator version for the run folder."""
    sha = _cmd_output(["git", "rev-parse", "--short", "HEAD"])
    dirty_out = _cmd_output(["git", "status", "--porcelain"], default="")
    iverilog_ver = _cmd_output(["iverilog", "-V"], default="iverilog not found")
    return Provenance(
        timestamp=timestamp,
        git_commit=sha,
        git_dirty=bool(dirty_out),
        docker_image="spec-fidelity",
        iverilog_version=iverilog_ver,
    )


def _call_repair(
    config: ExperimentConfig,
    current_tb_code: str,
    feedback_text: str,
    history: list[dict[str, str]],
    seed: int,
    llm_fn: Callable,
) -> tuple[str, list[LLMCall], list[dict[str, str]]]:
    """Execute one repair step (optional root_cause call + fix call) and return updated code."""
    rc_prompt, fix_prompt = build_repair_prompts(
        current_tb_code, feedback_text, config.feedback
    )
    active_msgs = list(history) if config.feedback.history == "full" else []
    calls: list[LLMCall] = []

    if rc_prompt:
        active_msgs.append({"role": "user", "content": rc_prompt})
        rc_call = llm_fn(config.model, list(active_msgs), seed=seed)
        calls.append(rc_call)
        active_msgs.append({"role": "assistant", "content": rc_call.response})

    active_msgs.append({"role": "user", "content": fix_prompt})
    fix_call = llm_fn(config.model, list(active_msgs), seed=seed)
    calls.append(fix_call)
    active_msgs.append({"role": "assistant", "content": fix_call.response})

    new_history = active_msgs if config.feedback.history == "full" else history
    return extract_code_block(fix_call.response), calls, new_history


def run_design(
    config: ExperimentConfig,
    design: Design,
    seed: int,
    design_run_dir: Path,
    llm_fn: Callable = call_llm,
) -> tuple[DesignRun, EvalResult]:
    """Run the generate -> test -> feedback -> fix loop and final evaluation for one design & seed."""
    design_run_dir = Path(design_run_dir)
    iters_root = design_run_dir / "iterations"
    iters_root.mkdir(parents=True, exist_ok=True)

    # Always ensure requirements are decomposed and saved (used in E2-E4 loop and in E1-E4 final_eval)
    decomp_call = ensure_requirements(design, config.model, llm_fn=llm_fn)
    req_file = (REPO_ROOT / design.spec_path).parent / "requirements.yaml"
    if req_file.is_file():
        shutil.copy2(req_file, design_run_dir / "requirements.yaml")

    iterations: list[Iteration] = []
    history: list[dict[str, str]] = []
    current_tb_code = ""

    for idx in range(config.max_iterations):
        iter_dir = iters_root / f"iter_{idx}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        llm_calls: list[LLMCall] = []
        if idx == 0 and decomp_call is not None:
            llm_calls.append(decomp_call)

        sim_elapsed_total = 0.0

        if idx == 0:
            gen_prompt = build_generate_prompt(design, config.feedback)
            history.append({"role": "user", "content": gen_prompt})
            call_rec = llm_fn(config.model, list(history), seed=seed)
            llm_calls.append(call_rec)
            history.append({"role": "assistant", "content": call_rec.response})
            current_tb_code = extract_code_block(call_rec.response)

            tb_path = iter_dir / "testbench.sv"
            tb_path.write_text(current_tb_code)

            sim_start = time.monotonic()
            checks = run_iteration_checks(
                design, tb_path, iter_dir, config.simulation, config.testing
            )
            sim_elapsed_total += round(time.monotonic() - sim_start, 4)

        elif not config.feedback.decompose_requirements:
            # E1 (Monolithic): one repair pass for the whole specification per iteration
            prev_iter = iterations[-1]
            prev_dir = iters_root / f"iter_{idx - 1}"
            feedback_text = format_feedback(prev_iter.checks, config.feedback, iter_dir=prev_dir)
            current_tb_code, new_calls, history = _call_repair(
                config, current_tb_code, feedback_text, history, seed, llm_fn
            )
            llm_calls.extend(new_calls)

            tb_path = iter_dir / "testbench.sv"
            tb_path.write_text(current_tb_code)

            sim_start = time.monotonic()
            checks = run_iteration_checks(
                design, tb_path, iter_dir, config.simulation, config.testing
            )
            sim_elapsed_total += round(time.monotonic() - sim_start, 4)

        else:
            # E2-E4 (Decomposed): loop over each requirement group within the iteration
            prev_checks = iterations[-1].checks
            by_name = {c.name: c for c in prev_checks}
            tb_path = iter_dir / "testbench.sv"

            # If the previous iteration failed to compile, repair compilation first
            if "compile" in by_name and not by_name["compile"].passed:
                comp_fb = format_feedback(
                    [by_name["compile"]], config.feedback, iter_dir=iter_dir / "compile_fix"
                )
                current_tb_code, new_calls, history = _call_repair(
                    config, current_tb_code, comp_fb, history, seed, llm_fn
                )
                llm_calls.extend(new_calls)
                tb_path.write_text(current_tb_code)
                sim_start = time.monotonic()
                prev_checks = run_iteration_checks(
                    design, tb_path, iter_dir, config.simulation, config.testing
                )
                sim_elapsed_total += round(time.monotonic() - sim_start, 4)

            # Now iterate over each requirement group in design.requirements
            checks = prev_checks
            for req in design.requirements:
                if is_requirement_passing(checks, req.id):
                    continue

                req_dir = iter_dir / req.id
                req_fb = format_requirement_feedback(
                    checks, req, config.feedback, req_dir=req_dir
                )
                current_tb_code, new_calls, history = _call_repair(
                    config, current_tb_code, req_fb, history, seed, llm_fn
                )
                llm_calls.extend(new_calls)

                (req_dir / "testbench.sv").write_text(current_tb_code)
                tb_path.write_text(current_tb_code)

                sim_start = time.monotonic()
                checks = run_iteration_checks(
                    design, tb_path, iter_dir, config.simulation, config.testing
                )
                sim_elapsed_total += round(time.monotonic() - sim_start, 4)
                if all(c.passed for c in checks):
                    break

        (iter_dir / "llm_calls.json").write_text(
            json.dumps([asdict(c) for c in llm_calls], indent=2) + "\n"
        )
        all_passed = all(c.passed for c in checks)

        iterations.append(
            Iteration(
                index=idx,
                testbench_path=f"iterations/iter_{idx}/testbench.sv",
                llm_calls=llm_calls,
                checks=checks,
                passed=all_passed,
                sim_wall_time_s=round(sim_elapsed_total, 4),
            )
        )
        if all_passed:
            break

    # Copy the winning (or last) iteration's testbench to final/testbench.sv
    final_dir = design_run_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    last_tb = design_run_dir / iterations[-1].testbench_path
    shutil.copy2(last_tb, final_dir / "testbench.sv")

    all_calls = [c for it in iterations for c in it.llm_calls]
    design_run = DesignRun(
        design=design.name,
        seed=seed,
        iterations=iterations,
        final_testbench="final/testbench.sv",
        final_passed=iterations[-1].passed,
        total_tokens=sum(c.prompt_tokens + c.completion_tokens for c in all_calls),
        num_llm_calls=len(all_calls),
        total_cost_usd=round(sum(c.cost_usd for c in all_calls), 6),
        llm_wall_time_s=round(sum(c.wall_time_s for c in all_calls), 4),
        sim_wall_time_s=round(sum(it.sim_wall_time_s for it in iterations), 4),
    )
    (design_run_dir / "run.json").write_text(
        json.dumps(asdict(design_run), indent=2) + "\n"
    )

    # Final stage: compose and run Section 4.1 evaluations (`config.final_eval.metrics`)
    eval_result = run_final_evaluations(
        design, design_run, design_run_dir, config.simulation, config.final_eval
    )
    return design_run, eval_result


def write_summary(run_root: Path, experiment_name: str, model_id: str, evals: list[EvalResult]) -> dict:
    """Aggregate all EvalResults in a run folder into summary.json."""
    n = len(evals) or 1
    summary = {
        "experiment": experiment_name,
        "model": model_id,
        "run_folder": str(run_root.relative_to(REPO_ROOT)) if run_root.is_relative_to(REPO_ROOT) else str(run_root),
        "num_trials": len(evals),
        # 4.1.3 Golden RTL Acceptance
        "compile_pass_rate": round(sum(e.compiles for e in evals) / n, 4),
        "golden_rtl_acceptance_rate": round(sum(e.golden_rtl_passed for e in evals) / n, 4),
        "false_positive_rate": round(sum(e.false_positive for e in evals) / n, 4),
        # 4.1.2 Mutation Testing
        "avg_mutation_score": round(sum(e.mutation_score for e in evals) / n, 4),
        # 4.1.5 Code Coverage
        "avg_code_coverage": round(sum(e.code_coverage_score for e in evals) / n, 4),
        # 4.1.6 Requirement Group Coverage
        "avg_req_group_coverage": round(sum(e.req_group_coverage_score for e in evals) / n, 4),
        # 4.1.7 Functional Coverage
        "avg_functional_coverage": round(sum(e.functional_coverage_score for e in evals) / n, 4),
        # 4.1.1 FixMe Golden TB Comparison
        "avg_missed_scenarios_vs_golden": round(sum(len(e.missed_scenarios_vs_golden) for e in evals) / n, 2),
        # 4.1.4 Computational Cost
        "avg_turns": round(sum(e.turns for e in evals) / n, 2),
        "total_llm_calls": sum(e.num_llm_calls for e in evals),
        "total_tokens": sum(e.total_tokens for e in evals),
        "total_cost_usd": round(sum(e.total_cost_usd for e in evals), 6),
        "total_llm_wall_time_s": round(sum(e.llm_wall_time_s for e in evals), 2),
        "total_sim_wall_time_s": round(sum(e.sim_wall_time_s for e in evals), 2),
        "per_trial": [asdict(e) for e in evals],
    }
    (run_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_experiment(config_path: str, llm_fn: Callable = call_llm) -> Path:
    """Load config, create runs/<experiment>/<timestamp>_<git_sha>/, and run all designs."""
    config = load_experiment(config_path)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d_%H%M%S")
    prov = collect_provenance(now.isoformat())

    run_root = REPO_ROOT / "runs" / config.name / f"{ts}_{prov.git_commit}"
    run_root.mkdir(parents=True, exist_ok=True)

    (run_root / "config.yaml").write_text(yaml.safe_dump(asdict(config), sort_keys=False))
    (run_root / "provenance.json").write_text(json.dumps(asdict(prov), indent=2) + "\n")

    evals: list[EvalResult] = []
    for d_rel in config.designs.paths:
        design = load_design(REPO_ROOT / d_rel)
        for seed in config.seeds:
            trial_dir = run_root / f"{design.name}__seed{seed}"
            print(f"[{config.name}] running {design.name} (seed={seed})...")
            _, eval_res = run_design(config, design, seed, trial_dir, llm_fn=llm_fn)
            evals.append(eval_res)
            print(
                f"  -> golden_accept={eval_res.golden_rtl_passed}, "
                f"mutation_score={eval_res.mutation_score:.0%}, "
                f"code_cov={eval_res.code_coverage_score:.0%}, "
                f"req_cov={eval_res.req_group_coverage_score:.0%}, "
                f"func_cov={eval_res.functional_coverage_score:.0%}, "
                f"turns={eval_res.turns}"
            )

    write_summary(run_root, config.name, config.model.model_id, evals)
    print(f"[{config.name}] finished -> {run_root.relative_to(REPO_ROOT)}")
    return run_root


def reevaluate_run(run_root: Path) -> dict:
    """Re-run only the final evaluation stage on an existing run folder."""
    run_root = Path(run_root).resolve()
    cfg_dict = yaml.safe_load((run_root / "config.yaml").read_text())
    sim = SimulationConfig(**cfg_dict["simulation"])
    final_cfg = FinalEvalConfig(**cfg_dict["final_eval"])
    design_map = {
        load_design(REPO_ROOT / p).name: load_design(REPO_ROOT / p)
        for p in cfg_dict["designs"]["paths"]
    }

    evals: list[EvalResult] = []
    for run_json in sorted(run_root.glob("*__seed*/run.json")):
        trial_dir = run_json.parent
        raw_run = json.loads(run_json.read_text())
        iters = [
            Iteration(
                index=it["index"],
                testbench_path=it["testbench_path"],
                llm_calls=[LLMCall(**c) for c in it["llm_calls"]],
                checks=[CheckResult(**ch) for ch in it["checks"]],
                passed=it["passed"],
                sim_wall_time_s=float(it.get("sim_wall_time_s", 0.0)),
            )
            for it in raw_run["iterations"]
        ]
        design_run = DesignRun(
            design=raw_run["design"],
            seed=raw_run["seed"],
            iterations=iters,
            final_testbench=raw_run["final_testbench"],
            final_passed=raw_run["final_passed"],
            total_tokens=raw_run["total_tokens"],
            num_llm_calls=int(raw_run.get("num_llm_calls", sum(len(it.llm_calls) for it in iters))),
            total_cost_usd=raw_run["total_cost_usd"],
            llm_wall_time_s=float(raw_run.get("llm_wall_time_s", raw_run.get("total_wall_time_s", 0.0))),
            sim_wall_time_s=float(raw_run.get("sim_wall_time_s", 0.0)),
        )
        evals.append(
            run_final_evaluations(
                design_map[design_run.design], design_run, trial_dir, sim, final_cfg
            )
        )

    return write_summary(run_root, cfg_dict["name"], cfg_dict["model"]["model_id"], evals)


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--eval-only":
        reevaluate_run(Path(args[1]))
        return 0
    if len(args) == 1:
        run_experiment(args[0])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
