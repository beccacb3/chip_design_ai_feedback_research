"""4. In-loop testing: runs the checks listed in ExperimentConfig.feedback."""

from pathlib import Path
from framework.models import CheckResult, Design, FeedbackConfig


def run_checks(design: Design, testbench_path: Path, checks: list[FeedbackConfig]) -> list[CheckResult]:
    """Run each configured feedback check on testbench_path and return CheckResults."""
    raise NotImplementedError
