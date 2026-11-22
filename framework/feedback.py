"""Feedback generation: formats failed CheckResults into feedback.md and builds prompts.

Because each check in `evaluation/testbench.py` writes its own self-contained
`CheckResult.summary`, `format_feedback` works with any combination of tests in
`ExperimentConfig.testing`.
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
            sections.append(f"### {r.name} failed\n" + "\n".join(lines))

    feedback_text = "\n\n".join(sections)
    if iter_dir is not None:
        Path(iter_dir).mkdir(parents=True, exist_ok=True)
        (Path(iter_dir) / "feedback.md").write_text(feedback_text + ("\n" if feedback_text else ""))
    return feedback_text


def build_generate_prompt(design: Design, cfg: FeedbackConfig) -> str:
    """Fill `generate_prompt` with `{top_module}` and `{spec}`."""
    template = (REPO_ROOT / cfg.generate_prompt).read_text()
    spec_text = (REPO_ROOT / design.spec_path).read_text().strip()
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
