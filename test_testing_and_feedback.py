"""Tests for atomic test functions (evaluation/testbench.py), dispatcher (framework/testing.py),
and feedback formatting (framework/feedback.py)."""

from pathlib import Path
from tempfile import TemporaryDirectory

from designs.standardize import load_design
from evaluation.testbench import (
    check_compile,
    check_coverage,
    check_mutations,
    check_simulate,
)
from framework.config import load_experiment
from framework.feedback import (
    build_generate_prompt,
    build_repair_prompts,
    format_feedback,
)
from framework.models import SimulationConfig, TestingConfig
from framework.testing import run_iteration_checks


def test_atomic_checks_on_golden_tb():
    design = load_design(Path("designs/examples/counter4"))
    tb_path = Path("designs/examples/counter4/golden/tb/counter4_tb.sv")
    sim = SimulationConfig(name="iverilog", tool="iverilog", args=["-g2012"], timeout_s=10)

    with TemporaryDirectory() as tmp:
        iter_dir = Path(tmp) / "iter_0"

        r_comp = check_compile(design, tb_path, iter_dir, sim, TestingConfig(name="compile"))
        assert r_comp.passed, r_comp.summary
        assert (iter_dir / "compile.log").exists()

        r_sim = check_simulate(design, tb_path, iter_dir, sim, TestingConfig(name="simulate"))
        assert r_sim.passed, r_sim.summary
        assert (iter_dir / "sim.log").exists()

        r_cov = check_coverage(
            design, tb_path, iter_dir, sim, TestingConfig(name="coverage", options={"min_coverage": 1.0})
        )
        assert r_cov.passed, r_cov.summary
        assert r_cov.details["coverage_score"] == 1.0
        assert (iter_dir / "coverage.json").exists()

        r_mut = check_mutations(
            design, tb_path, iter_dir, sim, TestingConfig(name="mutations", options={"min_kill_rate": 1.0})
        )
        assert r_mut.passed, r_mut.summary
        assert r_mut.details["mutation_score"] == 1.0
        assert (iter_dir / "mutations.json").exists()

    print("[PASS] Atomic checks (compile, simulate, coverage, mutations) on golden counter4_tb")


def test_incomplete_tb_triggers_coverage_and_mutation_feedback():
    """A testbench that only tests reset (never enables the counter) should:
      - pass compile and simulate,
      - fail coverage (the `else if (en)` branch is never hit),
      - fail mutations (`mutant_02_ignores_en.v` survives), and
      - produce formatted feedback.md listing both failures.
    """
    design = load_design(Path("designs/examples/counter4"))
    exp = load_experiment("configs/experiments/baseline.yaml")

    with TemporaryDirectory() as tmp:
        iter_dir = Path(tmp) / "iter_0"
        iter_dir.mkdir(parents=True)
        weak_tb = iter_dir / "testbench.sv"
        weak_tb.write_text(
            """`timescale 1ns/1ps
module tb;
    reg clk = 0, reset = 1, en = 0;
    wire [3:0] q;
    counter4 dut (.clk(clk), .reset(reset), .en(en), .q(q));
    always #5 clk = ~clk;
    initial begin
        @(posedge clk); #1;
        if (q !== 4'd0) $fatal(1, "Reset failed");
        $finish;
    end
endmodule
"""
        )

        checks_to_run = [
            TestingConfig(name="compile"),
            TestingConfig(name="simulate"),
            TestingConfig(name="coverage", options={"min_coverage": 1.0}),
            TestingConfig(name="mutations", options={"min_kill_rate": 1.0}),
        ]
        results = run_iteration_checks(design, weak_tb, iter_dir, exp.simulation, checks_to_run)
        by_name = {r.name: r for r in results}

        assert by_name["compile"].passed
        assert by_name["simulate"].passed
        assert not by_name["coverage"].passed
        assert not by_name["mutations"].passed
        assert "mutant_02_ignores_en.v" in by_name["mutations"].details["survived_list"]
        assert (iter_dir / "checks.json").exists()

        feedback_text = format_feedback(results, exp.feedback, iter_dir=iter_dir)
        assert "### coverage failed" in feedback_text
        assert "### mutations failed" in feedback_text
        assert "mutant_02_ignores_en.v" in feedback_text
        assert (iter_dir / "feedback.md").exists()

        gen_prompt = build_generate_prompt(design, exp.feedback)
        assert "counter4" in gen_prompt

        rc_prompt, fix_prompt = build_repair_prompts(weak_tb.read_text(), feedback_text, exp.feedback)
        assert rc_prompt is not None and "mutant_02_ignores_en.v" in rc_prompt
        assert fix_prompt

    print("[PASS] Incomplete testbench caught by coverage & mutations and formatted into feedback.md")


def main():
    test_atomic_checks_on_golden_tb()
    test_incomplete_tb_triggers_coverage_and_mutation_feedback()
    print("\nALL TESTING & FEEDBACK TESTS PASSED")


if __name__ == "__main__":
    main()
