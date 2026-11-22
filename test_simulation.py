
"""Tests for the Icarus Verilog simulation wrapper.

Tests:
    1. Basic compilation and simulation
    2. Compilation error detection
    3. Simulation failure detection
    4. Golden counter4 RTL validation
    5. Bad-reset mutant detection
    6. Ignored-enable mutant detection
    7. FIXME dffr_async RTL validation
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from framework.simulation import compile_verilog, run_simulation


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


def test_fixme_dffr_async(folder):
    print("\n========== TEST 7: FIXME DFFR_ASYNC ==========")

    base = Path("designs/fixme/dffr_async/golden")
    rtl = base / "rtl/dffr_async.v"
    tb = base / "tb/dffr_async_tb.sv"

    binary = folder / "dffr_async.out"

    compiled, diagnostics = compile_verilog(
        [rtl, tb],
        binary,
        args=["-s", "dffr_async_tb"],
    )

    print("Compilation:", compiled)

    if not compiled:
        print("Diagnostics:", diagnostics.strip())
        report("FIXME dffr_async validation", False)
        return

    passed, stdout, stderr = run_simulation(binary)

    print("Simulation:", passed)
    print("Output:", stdout.strip())
    print("Errors:", stderr.strip())

    report(
        "FIXME dffr_async validation",
        passed and "ALL DFFR_ASYNC TESTS PASSED" in stdout,
    )


def main():
    with TemporaryDirectory() as directory:
        folder = Path(directory)

        test_basic_simulation(folder)
        test_compilation_failure(folder)
        test_simulation_failure(folder)
        test_counter4(folder)
        test_fixme_dffr_async(folder)

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
