"""5. Feedback generation: formats failed CheckResults into text for the fix prompts."""

from framework.models import CheckResult


def format_feedback(results: list[CheckResult]) -> str:
    """Combine failed CheckResults into the `{feedback}` string for find_root_cause.md."""
    raise NotImplementedError
