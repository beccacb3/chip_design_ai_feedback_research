"""Tests for evaluation/final.py, framework/control_loop.py, and evaluation/report.py."""

from pathlib import Path
from tempfile import TemporaryDirectory

from designs.standardize import load_design
from evaluation.final import eval_assertion_audit, eval_false_positive
from evaluation.report import build_report
from framework.config import load_experiment
from framework.control_loop import run_design, write_summary
from framework.models import CheckResult, DesignRun, LLMCall

WEAK_TB = """`timescale 1ns/1ps
module tb;
    reg clk = 0, reset = 1, en = 0;
    wire [3:0] q;
    counter4 dut (.clk(clk), .reset(reset), .en(en), .q(q));
    always #5 clk = ~clk;
    initial begin
        @(posedge clk); #1;
        if (q !== 4'd0) $fatal(1, "Reset failed");
        if (q !== 4'd0) $fatal(1, "Second reset check");
        $finish;
    end
endmodule
"""

VACUOUS_TB = """`timescale 1ns/1ps
module tb;
    reg clk = 0, reset = 0, en = 0;
    wire [3:0] q;
    counter4 dut (.clk(clk), .reset(reset), .en(en), .q(q));
    initial $finish;
endmodule
"""


def test_final_only_evaluations():
    with TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        (run_dir / "iterations" / "iter_0").mkdir(parents=True)
        (run_dir / "final").mkdir(parents=True)

        (run_dir / "iterations" / "iter_0" / "testbench.sv").write_text(WEAK_TB)
        (run_dir / "final" / "testbench.sv").write_text(VACUOUS_TB)

        dummy_run = DesignRun(
            design="counter4",
            seed=0,
            iterations=[],
            final_testbench="final/testbench.sv",
            final_passed=True,
            total_tokens=100,
            total_cost_usd=0.001,
            total_wall_time_s=1.0,
        )

        # 1. False positive check: compiled=True, simulate=False -> false_positive=True (fails check)
        fp_res = eval_false_positive(
            dummy_run,
            run_dir,
            {
                "compile": CheckResult(name="compile", passed=True, summary=""),
                "simulate": CheckResult(name="simulate", passed=False, summary=""),
            },
        )
        assert not fp_res.passed
        assert fp_res.details["false_positive"] is True

        # 2. Assertion audit: iter_0 had checks, final has 0 checks -> flagged as vacuous/gaming
        audit_res = eval_assertion_audit(
            dummy_run,
            run_dir,
            {"mutations": CheckResult(name="mutations", passed=False, summary="")},
        )
        assert not audit_res.passed
        assert audit_res.details["vacuous"] is True
        assert audit_res.details["deleted_checks"] > 0

    print("[PASS] Final-only evaluations (false_positive, assertion_audit)")


def test_control_loop_and_final_stage():
    """Simulate a 2-iteration run on counter4:
      - Call 1 (iter_0 generate): returns WEAK_TB (misses mutant_02_ignores_en.v).
      - Call 2 (iter_1 root_cause): analyzes why mutant_02 survived.
      - Call 3 (iter_1 fix): returns the golden counter4_tb.sv (kills all mutants).
      - Final stage composes all 8 final_eval metrics and writes final/eval.json + summary.json.
    """
    design = load_design(Path("designs/examples/counter4"))
    config = load_experiment("configs/experiments/level4_mutations.yaml")
    golden_tb = Path("designs/examples/counter4/golden/tb/counter4_tb.sv").read_text()

    responses = [
        f"```systemverilog\n{WEAK_TB}\n```",
        "Root cause: the testbench never asserts `en = 1` to test counting.",
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
        run_root = runs_root / "baseline" / "2026-11-22_test"
        trial_dir = run_root / "counter4__seed0"

        design_run, eval_res = run_design(
            config, design, seed=0, design_run_dir=trial_dir, llm_fn=fake_llm
        )

        # Verify iteration 0 failed mutations and wrote feedback.md, and iteration 1 passed
        assert len(design_run.iterations) == 2
        assert not design_run.iterations[0].passed
        assert (trial_dir / "iterations" / "iter_0" / "feedback.md").exists()
        assert design_run.iterations[1].passed
        assert design_run.final_passed

        # Verify final stage composed both testbench checks and final-only evaluations
        assert eval_res.compiles is True
        assert eval_res.golden_rtl_passed is True
        assert eval_res.false_positive is False
        assert eval_res.coverage_score == 1.0
        assert eval_res.mutation_score == 1.0
        assert eval_res.turns == 2
        assert eval_res.total_tokens == 450
        assert eval_res.assertion_audit_passed is True
        assert (trial_dir / "final" / "eval.json").exists()
        assert (trial_dir / "run.json").exists()

        write_summary(run_root, config.name, config.model.model_id, [eval_res])
        table = build_report(runs_root)
        assert "level4_mutations" in table
        assert "100%" in table

    print("[PASS] End-to-end control_loop + composed final evaluation + report table")


def main():
    test_final_only_evaluations()
    test_control_loop_and_final_stage()
    print("\nALL CONTROL LOOP & FINAL EVALUATION TESTS PASSED")


if __name__ == "__main__":
    main()
