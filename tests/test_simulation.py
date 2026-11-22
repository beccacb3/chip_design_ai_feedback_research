
"""Tests for the Icarus Verilog simulation wrapper.

Tests:
    1. Basic compilation and simulation
    2. Compilation error detection
    3. Simulation failure detection
    4. Golden counter4 RTL validation
    5. Bad-reset mutant detection
    6. Ignored-enable mutant detection
    7. FIXME dffr_async RTL validation
    8. FIXME alu_select RTL validation
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from evaluation.simulation import compile_verilog, run_simulation


results = []


def report(name, success, details=""):
    """Print and record a test result."""
    status = "PASS" if success else "FAIL"

    print(f"\n[{status}] {name}")

    if details:
        print(details.strip())

    results.append((name, success))


def test_basic_simulation(folder):
    print("\n========== TEST 1: BASIC SIMULATION ==========")

    tb = folder / "basic_tb.sv"
    tb.write_text("""
module basic_tb;
    initial begin
        $display("TEST PASSED");
        $finish;
    end
endmodule
""")

    binary = folder / "basic.out"

    compiled, diagnostics = compile_verilog([tb], binary)

    print("Compilation:", compiled)
    print("Diagnostics:", diagnostics.strip())

    if not compiled:
        report("Basic compilation and simulation", False)
        return

    passed, stdout, stderr = run_simulation(binary)

    print("Simulation:", passed)
    print("Output:", stdout.strip())
    print("Errors:", stderr.strip())

    report(
        "Basic compilation and simulation",
        passed and "TEST PASSED" in stdout,
    )


def test_compilation_failure(folder):
    print("\n========== TEST 2: COMPILATION ERROR ==========")

    tb = folder / "invalid_tb.sv"
    tb.write_text("""
module invalid_tb;
    this is invalid verilog syntax;
endmodule
""")

    binary = folder / "invalid.out"

    compiled, diagnostics = compile_verilog([tb], binary)

    print("Compilation:", compiled)
    print("Diagnostics:", diagnostics.strip())

    report(
        "Compilation error detection",
        not compiled and bool(diagnostics.strip()),
    )


def test_simulation_failure(folder):
    print("\n========== TEST 3: SIMULATION FAILURE ==========")

    tb = folder / "failing_tb.sv"
    tb.write_text("""
module failing_tb;
    initial begin
        $fatal(1, "Intentional simulation failure");
    end
endmodule
""")

    binary = folder / "failing.out"

    compiled, diagnostics = compile_verilog([tb], binary)

    if not compiled:
        print("Compilation diagnostics:", diagnostics.strip())
        report("Simulation failure detection", False)
        return

    passed, stdout, stderr = run_simulation(binary)

    print("Compilation:", compiled)
    print("Simulation:", passed)
    print("Output:", stdout.strip())
    print("Errors:", stderr.strip())

    report(
        "Simulation failure detection",
        not passed and "Intentional simulation failure" in (
            stdout + stderr
        ),
    )


def test_counter4(folder):
    print("\n========== TEST 4: COUNTER4 RTL & MUTANTS ==========")

    base = Path("designs/examples/counter4/golden")
    tb = base / "tb/counter4_tb.sv"

    designs = [
        (
            "Golden counter4 RTL",
            base / "rtl/counter4.v",
            True,
        ),
        (
            "Bad-reset mutant",
            base / "mutants/mutant_01_bad_reset.v",
            False,
        ),
        (
            "Ignored-enable mutant",
            base / "mutants/mutant_02_ignores_en.v",
            False,
        ),
    ]

    for name, rtl, expected_pass in designs:
        print(f"\n--- {name} ---")

        binary = folder / f"{rtl.stem}.out"

        compiled, diagnostics = compile_verilog(
            [rtl, tb],
            binary,
            args=["-s", "counter4_tb"],
        )

        print("Compilation:", compiled)

        if not compiled:
            print("Diagnostics:", diagnostics.strip())
            report(name, False)
            continue

        passed, stdout, stderr = run_simulation(binary)

        print("Simulation:", passed)
        print("Output:", stdout.strip())
        print("Errors:", stderr.strip())

        report(
            name,
            passed == expected_pass,
        )


def run_design_and_mutants(folder, title, base, tb, cases, top_tb=None):
    print(f"\n========== {title} ==========")
    args = ["-s", top_tb] if top_tb else []
    for name, rtl, expected_pass in cases:
        print(f"\n--- {name} ---")
        binary = folder / f"{title}_{rtl.stem}.out"
        compiled, diagnostics = compile_verilog([rtl, tb], binary, args=args)
        print("Compilation:", compiled)
        if not compiled:
            print("Diagnostics:", diagnostics.strip())
            report(name, False)
            continue
        passed, stdout, stderr = run_simulation(binary)
        print("Simulation:", passed)
        print("Output:", stdout.strip())
        print("Errors:", stderr.strip())
        report(name, passed == expected_pass)


def test_fixme_dffr_async(folder):
    base = Path("designs/fixme/dffr_async/golden")
    run_design_and_mutants(
        folder,
        "TEST 7: FIXME DFFR_ASYNC & MUTANTS",
        base,
        base / "tb/dffr_async_tb.sv",
        [
            ("FIXME dffr_async golden RTL", base / "rtl/dffr_async.v", True),
            ("FIXME dffr_async bad-reset mutant", base / "mutants/mutant_01_bad_reset.v", False),
            ("FIXME dffr_async swapped-scan-mux mutant", base / "mutants/mutant_02_swapped_scan_mux.v", False),
        ],
        top_tb="dffr_async_tb",
    )


def test_fixme_alu_select(folder):
    base = Path("designs/fixme/alu_select/golden")
    run_design_and_mutants(
        folder,
        "TEST 8: FIXME ALU_SELECT & MUTANTS",
        base,
        base / "tb/alu_select_tb.sv",
        [
            ("FIXME alu_select golden RTL", base / "rtl/alu_select.v", True),
            ("FIXME alu_select inverted-oe mutant", base / "mutants/mutant_01_inverted_oe.v", False),
            ("FIXME alu_select swapped-op-sel mutant", base / "mutants/mutant_02_swapped_op_sel.v", False),
        ],
        top_tb="alu_select_tb",
    )


def test_fixme_mux(folder):
    base = Path("designs/fixme/mux/golden")
    run_design_and_mutants(
        folder,
        "TEST 9: FIXME MUX & MUTANTS",
        base,
        base / "tb/tb_top.sv",
        [
            ("FIXME mux golden RTL", base / "rtl/mux.sv", True),
            ("FIXME mux inverted-mux1-out mutant", base / "mutants/mutant_01_inverted_mux1_out.sv", False),
        ],
        top_tb="tb_top",
    )


def test_fixme_syncrstz(folder):
    base = Path("designs/fixme/syncrstz/golden")
    run_design_and_mutants(
        folder,
        "TEST 10: FIXME SYNCRSTZ & MUTANTS",
        base,
        base / "tb/syncrstz_tb.sv",
        [
            ("FIXME syncrstz golden RTL", base / "rtl/syncrstz.v", True),
            ("FIXME syncrstz negedge-clk mutant", base / "mutants/mutant_01_negedge_clk.v", False),
            ("FIXME syncrstz reversed-shift mutant", base / "mutants/mutant_02_reversed_shift.v", False),
        ],
        top_tb="tb_top",
    )


def main():
    with TemporaryDirectory() as directory:
        folder = Path(directory)

        test_basic_simulation(folder)
        test_compilation_failure(folder)
        test_simulation_failure(folder)
        test_counter4(folder)
        test_fixme_dffr_async(folder)
        test_fixme_alu_select(folder)
        test_fixme_mux(folder)
        test_fixme_syncrstz(folder)

    print("\n" + "=" * 50)
    print("FINAL TEST SUMMARY")
    print("=" * 50)

    for name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"[{status}] {name}")

    passed_count = sum(success for _, success in results)
    total_count = len(results)

    print(f"\nTests passed: {passed_count}/{total_count}")

    if passed_count == total_count:
        print("ALL SIMULATION TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
