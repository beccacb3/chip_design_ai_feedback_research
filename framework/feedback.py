"""Feedback generation: formats failed CheckResults into feedback.md and builds prompts.

In E1 (`decompose_requirements: false`), the agent receives the monolithic
specification. In E2-E4 (`decompose_requirements: true`), the specification is
accompanied by the decomposed requirement groups (`[REQ_ID]`) so simulation,
code coverage, and functional coverage feedback map directly to requirement groups.
"""

from pathlib import Path

from framework.models import CheckResult, Design, FeedbackConfig

REPO_ROOT = Path(__file__).resolve().parent.parent


def format_feedback(
    results: list[CheckResult],
    cfg: FeedbackConfig,
    iter_dir: Path | None = None,
) -> str:
    """Combine failed CheckResults into `{feedback}` text and optionally save feedback.md."""
    sections = []
    for r in results:
        if not r.passed:
            lines = r.summary.splitlines()[: cfg.max_error_lines]
            sections.append(f"### {r.name} feedback\n" + "\n".join(lines))

    feedback_text = "\n\n".join(sections)
    if iter_dir is not None:
        Path(iter_dir).mkdir(parents=True, exist_ok=True)
        (Path(iter_dir) / "feedback.md").write_text(feedback_text + ("\n" if feedback_text else ""))
    return feedback_text


def format_requirement_groups(design: Design) -> str:
    """Format decomposed requirement groups for E2-E4 prompts."""
    if not design.requirements:
        return ""
    lines = [
        "\n\n## Decomposed Requirement Groups",
        "Tag each test case and `$fatal` message with its requirement group ID in brackets (e.g. `[REQ_ID]`):",
    ]
    for req in design.requirements:
        cps = ", ".join(req.coverpoints.keys())
        lines.append(f"- **`[{req.id}]`**: {req.description} (scenarios: {cps})")
    return "\n".join(lines)


def build_generate_prompt(design: Design, cfg: FeedbackConfig) -> str:
    """Fill `generate_prompt` with `{top_module}` and `{spec}` (plus requirement groups in E2-E4)."""
    template = (REPO_ROOT / cfg.generate_prompt).read_text()
    spec_text = (REPO_ROOT / design.spec_path).read_text().strip()
    if cfg.decompose_requirements:
        spec_text += format_requirement_groups(design)
    return template.format(top_module=design.top_module, spec=spec_text)


def build_repair_prompts(
    tb_code: str,
    feedback_text: str,
    cfg: FeedbackConfig,
) -> tuple[str | None, str]:
    """Return (root_cause_prompt_or_None, fix_prompt) filled with `{feedback}` and `{testbench}`."""
    root_cause = None
    if cfg.root_cause_prompt:
        rc_template = (REPO_ROOT / cfg.root_cause_prompt).read_text()
        root_cause = rc_template.format(feedback=feedback_text, testbench=tb_code)

    fix_template = (REPO_ROOT / cfg.fix_prompt).read_text()
    if "{feedback}" in fix_template or "{testbench}" in fix_template:
        fix = fix_template.format(feedback=feedback_text, testbench=tb_code)
    else:
        fix = fix_template
    return root_cause, fix
