"""Feedback generation and LLM specification decomposition:
  - `decompose_design_requirements` / `ensure_requirements`: calls the LLM with
    `prompts/decompose_spec.md` to decompose `spec.md` into requirement groups and
    saves them to `designs/<group>/<name>/requirements.yaml` (`generated_by: llm`).
  - `format_feedback`: formats monolithic feedback for E1.
  - `is_requirement_passing` & `format_requirement_feedback`: checks and formats
    localized feedback for a single requirement group `req` in E2-E4.
"""

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Callable

import yaml

from framework.llm import call_llm
from framework.models import (
    CheckResult,
    Design,
    FeedbackConfig,
    LLMCall,
    ModelConfig,
    RequirementGroup,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

YAML_BLOCK_RE = re.compile(r"```(?:yaml|yml)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


# --------------------------------------------------------------------- LLM spec decomposition


def _numbered_rtl(design: Design) -> str:
    blocks = []
    for rel_path in design.golden_rtl:
        p = REPO_ROOT / rel_path
        numbered = "\n".join(
            f"{i:4d}: {line}" for i, line in enumerate(p.read_text().splitlines(), start=1)
        )
        blocks.append(f"// File: {p.name}\n{numbered}")
    return "\n\n".join(blocks)


def decompose_design_requirements(
    design: Design,
    model: ModelConfig,
    out_path: Path | None = None,
    llm_fn: Callable = call_llm,
) -> tuple[list[RequirementGroup], LLMCall]:
    """Use the LLM to decompose `spec.md` into RequirementGroups and save requirements.yaml."""
    template = (REPO_ROOT / "prompts/decompose_spec.md").read_text()
    spec_text = (REPO_ROOT / design.spec_path).read_text().strip()
    prompt = template.format(
        top_module=design.top_module,
        spec=spec_text,
        numbered_rtl=_numbered_rtl(design),
    )

    llm_call = llm_fn(model, prompt, seed=0)
    matches = YAML_BLOCK_RE.findall(llm_call.response)
    yaml_text = matches[-1] if matches else llm_call.response
    parsed = yaml.safe_load(yaml_text) or {}
    raw_reqs = parsed.get("requirements", parsed if isinstance(parsed, list) else [])

    reqs = [
        RequirementGroup(
            id=str(r["id"]).strip(),
            description=str(r["description"]).strip(),
            rtl_lines=[int(x) for x in r.get("rtl_lines", [])],
            coverpoints={str(k): str(v) for k, v in (r.get("coverpoints") or {}).items()},
        )
        for r in raw_reqs
    ]

    if out_path is None:
        out_path = (REPO_ROOT / design.spec_path).parent / "requirements.yaml"
    payload = {
        "generated_by": "llm",
        "model": model.model_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "requirements": [asdict(r) for r in reqs],
    }
    Path(out_path).write_text(yaml.safe_dump(payload, sort_keys=False))
    design.requirements = reqs
    return reqs, llm_call


def ensure_requirements(
    design: Design,
    model: ModelConfig,
    llm_fn: Callable = call_llm,
) -> LLMCall | None:
    """Ensure `design.requirements` is loaded from `requirements.yaml`, or decompose via LLM if missing."""
    req_file = (REPO_ROOT / design.spec_path).parent / "requirements.yaml"
    if design.requirements and req_file.is_file():
        return None
    if req_file.is_file():
        data = yaml.safe_load(req_file.read_text()) or {}
        design.requirements = [RequirementGroup(**r) for r in data.get("requirements", [])]
        if design.requirements:
            return None
    _, call_rec = decompose_design_requirements(design, model, out_path=req_file, llm_fn=llm_fn)
    return call_rec


# --------------------------------------------------------------------- monolithic & per-requirement feedback


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


def is_requirement_passing(results: list[CheckResult], req_id: str) -> bool:
    """Return True if `req_id` passed every check in `results`."""
    by_name = {r.name: r for r in results}
    if "compile" in by_name and not by_name["compile"].passed:
        return False

    if "requirement_groups" in by_name:
        g = by_name["requirement_groups"].details.get("groups", {}).get(req_id, {})
        if not g.get("passed", False):
            return False

    if "req_code_coverage" in by_name:
        g = by_name["req_code_coverage"].details.get("per_requirement_group", {}).get(req_id, {})
        if float(g.get("coverage_score", 0.0)) < 1.0:
            return False

    if "req_functional_coverage" in by_name:
        g = by_name["req_functional_coverage"].details.get("per_requirement_group", {}).get(req_id, {})
        if float(g.get("functional_coverage_score", 0.0)) < 1.0:
            return False

    return True


def format_requirement_feedback(
    results: list[CheckResult],
    req: RequirementGroup,
    cfg: FeedbackConfig,
    req_dir: Path | None = None,
) -> str:
    """Build localized feedback specifically for one requirement group `req` (used in E2-E4)."""
    by_name = {r.name: r for r in results}
    lines = [
        f"### Requirement Group `[{req.id}]`",
        f"Requirement: {req.description}",
    ]

    if "simulate" in by_name and not by_name["simulate"].passed:
        sim_out = by_name["simulate"].details.get("stdout", "")
        sim_lines = sim_out.splitlines()[: cfg.max_error_lines]
        lines.append("Simulation output:\n" + "\n".join(f"  {ln}" for ln in sim_lines))

    if "requirement_groups" in by_name:
        g = by_name["requirement_groups"].details.get("groups", {}).get(req.id, {})
        status = "PASS" if g.get("passed") else ("FAIL" if g.get("assertion_failures") else "NOT EXERCISED")
        lines.append(f"- Group simulation status: {status}")
        if g.get("assertion_failures"):
            lines.append(f"- Assertion failures for [{req.id}]: {g['assertion_failures']}")

    if "req_code_coverage" in by_name:
        g = by_name["req_code_coverage"].details.get("per_requirement_group", {}).get(req.id, {})
        lines.append(
            f"- Requirement RTL code coverage: {g.get('coverage_score', 0.0):.0%} "
            f"(covered lines: {g.get('covered_lines', [])}, uncovered lines: {g.get('uncovered_lines', [])})"
        )

    if "req_functional_coverage" in by_name:
        g = by_name["req_functional_coverage"].details.get("per_requirement_group", {}).get(req.id, {})
        lines.append(
            f"- Requirement functional coverage: {g.get('functional_coverage_score', 0.0):.0%} "
            f"(hit scenarios: {g.get('hit_coverpoints', [])}, missed scenarios: {g.get('missed_coverpoints', [])})"
        )

    lines.append(
        f"\nUpdate the testbench to thoroughly test and verify `[{req.id}]` while keeping all other passing requirement groups intact."
    )
    feedback_text = "\n".join(lines)
    if req_dir is not None:
        Path(req_dir).mkdir(parents=True, exist_ok=True)
        (Path(req_dir) / "feedback.md").write_text(feedback_text + "\n")
    return feedback_text


def format_requirement_groups(design: Design) -> str:
    """Format decomposed requirement groups for E2-E4 generation prompts."""
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
