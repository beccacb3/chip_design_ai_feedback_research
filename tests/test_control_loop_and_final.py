"""Tests for Section 4.1 final evaluations (evaluation/final.py),
E1-E4 control loop (framework/control_loop.py), and report table (evaluation/report.py)."""

from pathlib import Path
from tempfile import TemporaryDirectory

from designs.standardize import load_design
from evaluation.final import eval_computational_cost, eval_golden_rtl_acceptance
from evaluation.report import build_report
from framework.config import load_experiment
from framework.control_loop import run_design, write_summary
from framework.models import CheckResult, DesignRun, LLMCall, SimulationConfig

WEAK_TB = """`timescale 1ns/1ps
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


def test_final_only_evaluations():
    sim = SimulationConfig(name="iverilog", tool="iverilog", args=["-g2012"], timeout_s=10)
    design = load_design(Path("designs/examples/counter4"))

    with TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        dummy_run = DesignRun(
            design="counter4",
            seed=0,
            iterations=[],
            final_testbench="final/testbench.sv",
            final_passed=True,
            total_tokens=250,
            num_llm_calls=3,
            total_cost_usd=0.0012,
            llm_wall_time_s=1.5,
            sim_wall_time_s=0.4,
        )

        # 4.1.3 Golden RTL Acceptance: compiled=True, simulate=False -> false_positive=True
        acc_res = eval_golden_rtl_acceptance(
            design,
            dummy_run,
            run_dir,
            sim,
            {
                "compile": CheckResult(name="compile", passed=True, summary=""),
                "simulate": CheckResult(name="simulate", passed=False, summary=""),
            },
        )
        assert not acc_res.passed
        assert acc_res.details["false_positive"] is True

        # 4.1.4 Computational Cost
        cost_res = eval_computational_cost(design, dummy_run, run_dir, sim, {})
        assert cost_res.passed
        assert cost_res.details["num_llm_calls"] == 3
        assert cost_res.details["sim_wall_time_s"] == 0.4

    print("[PASS] Section 4.1 final-only evaluations (golden_rtl_acceptance, computational_cost)")


def test_e4_control_loop_and_section_4_1_final_stage():
    """Simulate a 2-iteration E4 run on counter4:
      - Iteration 0: returns WEAK_TB (only exercises REQ_RESET; misses REQ_INCREMENT, REQ_HOLD, REQ_WRAP).
      - Iteration 1: receives localized E2/E3/E4 requirement-group feedback and returns golden counter4_tb.sv.
      - Final stage runs all 7 Section 4.1 evaluations (4.1.1 - 4.1.7) and writes final/eval.json + summary.json.
    """
    design = load_design(Path("designs/examples/counter4"))
    config = load_experiment("configs/experiments/e4_functional_coverage.yaml")
    golden_tb = Path("designs/examples/counter4/golden/tb/counter4_tb.sv").read_text()

    responses = [
        f"```systemverilog\n{WEAK_TB}\n```",
        "Root cause: REQ_INCREMENT, REQ_HOLD, and REQ_WRAP were not exercised.",
        f"```systemverilog\n{golden_tb}\n```",
    ]
    call_idx = 0

    def fake_llm(model, prompt, seed=None):
        nonlocal call_idx
        resp = responses[call_idx]
        call_idx += 1
        return LLMCall(
            model=model.model_id,
            prompt=str(prompt),
            response=resp,
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.0005,
            wall_time_s=0.25,
        )

    with TemporaryDirectory() as tmp:
        runs_root = Path(tmp) / "runs"
        run_root = runs_root / "e4_functional_coverage" / "2026-11-22_test"
        trial_dir = run_root / "counter4__seed0"

        design_run, eval_res = run_design(
            config, design, seed=0, design_run_dir=trial_dir, llm_fn=fake_llm
        )

        # Iteration 0 failed E2/E3/E4 requirement checks; Iteration 1 passed all of them
        assert len(design_run.iterations) == 2
        assert not design_run.iterations[0].passed
        assert (trial_dir / "iterations" / "iter_0" / "feedback.md").exists()
        assert design_run.iterations[1].passed
        assert design_run.final_passed
        assert design_run.num_llm_calls == 3

        # Verify all 7 Section 4.1 final evaluation metrics in EvalResult
        assert eval_res.compiles is True
        assert eval_res.golden_rtl_passed is True
        assert eval_res.false_positive is False
        assert eval_res.mutation_score == 1.0
        assert eval_res.code_coverage_score == 1.0
        assert eval_res.req_group_coverage_score == 1.0
        assert eval_res.functional_coverage_score == 1.0
        assert eval_res.missed_scenarios_vs_golden == []
        assert eval_res.turns == 2
        assert eval_res.num_llm_calls == 3
        assert eval_res.total_tokens == 450
        assert (trial_dir / "final" / "eval.json").exists()

        write_summary(run_root, config.name, config.model.model_id, [eval_res])
        table = build_report(runs_root)
        assert "e4_functional_coverage" in table
        assert "100%" in table

    print("[PASS] End-to-end E4 control_loop + Section 4.1.1-4.1.7 final evaluation + report table")


def main():
    test_final_only_evaluations()
    test_e4_control_loop_and_section_4_1_final_stage()
    print("\nALL CONTROL LOOP & FINAL EVALUATION TESTS PASSED")


if __name__ == "__main__":
    main()
