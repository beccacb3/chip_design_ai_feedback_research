"""Final evaluation: grades final/testbench.sv against designs/.../golden/.

Entry point for `make eval`:
    python3 -m evaluation.final runs/<experiment>/<timestamp>_<git_sha>
"""

from pathlib import Path
from framework.models import Design, EvalResult


def evaluate_design_run(design: Design, design_run_dir: Path) -> EvalResult:
    """Grade final/testbench.sv against golden/rtl/ and golden/mutants/ -> final/eval.json."""
    raise NotImplementedError


def evaluate_experiment_run(run_root: Path) -> dict:
    """Evaluate all <design>__seed<n>/ folders in run_root and write summary.json."""
    raise NotImplementedError
