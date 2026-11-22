"""Feedback generation: formats failed CheckResults into text for the fix prompts.

Because each check in `evaluation/testbench.py` writes its own human-readable
`CheckResult.summary`, `format_feedback` is test-agnostic and works with any
combination of checks in `ExperimentConfig.testing`.
"""

from framework.models import CheckResult, FeedbackConfig


def format_feedback(results: list[CheckResult], cfg: FeedbackConfig) -> str:
    """Combine failed CheckResults into the `{feedback}` string for the repair prompts."""
    sections = []
    for r in results:
        if not r.passed:
            lines = r.summary.splitlines()[: cfg.max_error_lines]
            sections.append(f"### {r.name} failed\n" + "\n".join(lines))
    return "\n\n".join(sections)
