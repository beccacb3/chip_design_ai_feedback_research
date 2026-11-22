"""1. Control flow loop: orchestrates generate -> test -> feedback -> fix.

Entry point for `make run`:
    python3 -m framework.control_loop configs/experiments/baseline.yaml
"""

from pathlib import Path
from framework.models import Design, DesignRun, ExperimentConfig


def run_design(config: ExperimentConfig, design: Design, seed: int, out_dir: Path) -> DesignRun:
    """Run the generate -> test -> feedback -> fix loop for one design and seed."""
    raise NotImplementedError


def run_experiment(config_path: str) -> Path:
    """Load config, create runs/<experiment>/<timestamp>_<git_sha>/, and run all designs."""
    raise NotImplementedError
