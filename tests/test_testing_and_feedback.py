"""Tests for E1-E4 testbench check functions (evaluation/testbench.py),
dispatcher (framework/testing.py), and feedback formatting (framework/feedback.py)."""

from pathlib import Path
from tempfile import TemporaryDirectory

from designs.standardize import load_design
from evaluation.testbench import (
    check_compile,
    check_mutations,
    check_req_code_coverage,
    check_req_functional_coverage,
    check_requirement_groups,
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
    sim = SimulationConfig(name="iverilog", tool="iverilog", args=["-g2012"], timeout_s=10)
    design_dirs = [
        "designs/examples/counter4",
        "designs/fixme/alu_select",
        "designs/fixme/dffr_async",
        "designs/fixme/mux",
        "designs/fixme/syncrstz",
    ]

    with TemporaryDirectory() as tmp:
        for d_rel in design_dirs:
            design = load_design(Path(d_rel))
            tb_path = Path(design.golden_tb[0])
            iter_dir = Path(tmp) / design.name

            r_comp = check_compile(design, tb_path, iter_dir, sim, TestingConfig(name="compile"))
            assert r_comp.passed, f"{design.name}: {r_comp.summary}"

            r_sim = check_simulate(design, tb_path, iter_dir, sim, TestingConfig(name="simulate"))
            assert r_sim.passed, f"{design.name}: {r_sim.summary}"

            r_req = check_requirement_groups(
                design, tb_path, iter_dir, sim, TestingConfig(name="requirement_groups")
            )
            assert r_req.passed, f"{design.name}: {r_req.summary}"
            assert r_req.details["req_group_coverage_score"] == 1.0

            r_cov = check_req_code_coverage(
                design, tb_path, iter_dir, sim, TestingConfig(name="req_code_coverage")
            )
            assert r_cov.passed, f"{design.name}: {r_cov.summary}"
            assert r_cov.details["coverage_score"] == 1.0

            r_fcov = check_req_functional_coverage(
                design, tb_path, iter_dir, sim, TestingConfig(name="req_functional_coverage")
            )
            assert r_fcov.passed, f"{design.name}: {r_fcov.summary}"
            assert r_fcov.details["functional_coverage_score"] == 1.0

            r_mut = check_mutations(
                design, tb_path, iter_dir, sim, TestingConfig(name="mutations")
            )
            assert r_mut.passed, f"{design.name}: {r_mut.summary}"
            assert r_mut.details["mutation_score"] == 1.0

    print("[PASS] Atomic checks (compile, simulate, requirement_groups, req_code_coverage, req_functional_coverage, mutations) on all 5 golden testbenches")


def test_incomplete_tb_triggers_e2_e3_e4_feedback():
    """A testbench that only tests reset (never enables the counter):
      - passes E1 (compile + simulate),
      - fails E2 (requirement_groups: REQ_INCREMENT, REQ_HOLD, REQ_WRAP not exercised),
      - fails E3 (req_code_coverage: line 9 uncovered),
      - fails E4 (req_functional_coverage: increment, hold, wrap coverpoints missed).
    """
    design = load_design(Path("designs/examples/counter4"))
    e1 = load_experiment("configs/experiments/e1_monolithic.yaml")
    e4 = load_experiment("configs/experiments/e4_functional_coverage.yaml")

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
        if (q !== 4'd0) $fatal(1, "[REQ_RESET] Reset failed");
        $finish;
    end
endmodule
"""
        )

        results = run_iteration_checks(design, weak_tb, iter_dir, e4.simulation, e4.testing)
        by_name = {r.name: r for r in results}

        assert by_name["compile"].passed
        assert by_name["simulate"].passed
        assert not by_name["requirement_groups"].passed
        assert not by_name["req_code_coverage"].passed
        assert not by_name["req_functional_coverage"].passed

        feedback_text = format_feedback(results, e4.feedback, iter_dir=iter_dir)
        assert "### requirement_groups feedback" in feedback_text
        assert "### req_code_coverage feedback" in feedback_text
        assert "### req_functional_coverage feedback" in feedback_text
        assert "REQ_WRAP" in feedback_text

        # E1 prompt has monolithic spec; E2-E4 prompt includes decomposed requirement groups
        p_e1 = build_generate_prompt(design, e1.feedback)
        p_e4 = build_generate_prompt(design, e4.feedback)
        assert "Decomposed Requirement Groups" not in p_e1
        assert "Decomposed Requirement Groups" in p_e4
        assert "REQ_RESET" in p_e4

        rc_prompt, fix_prompt = build_repair_prompts(weak_tb.read_text(), feedback_text, e4.feedback)
        assert rc_prompt is not None and "REQ_WRAP" in rc_prompt
        assert fix_prompt

    print("[PASS] Incomplete testbench passes E1 but triggers localized E2/E3/E4 requirement feedback")


def main():
    test_atomic_checks_on_golden_tb()
    test_incomplete_tb_triggers_e2_e3_e4_feedback()
    print("\nALL TESTING & FEEDBACK TESTS PASSED")


if __name__ == "__main__":
    main()
