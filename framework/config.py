"""Load experiment and component configs into dataclasses defined in framework/models.py.

Two simple rules apply to every YAML file in configs/:
  1. Top-level `extends:` starts from another YAML file; any key written in the
     child file replaces that key from the parent.
  2. An experiment file references its 6 sections by path:
     model, designs, simulation, testing (list), feedback, final_eval.

Usage (validate and print resolved config):
    python3 -m framework.config configs/experiments/baseline.yaml
"""

from dataclasses import asdict
from pathlib import Path
import sys

import yaml

from framework.models import (
    DesignsConfig,
    ExperimentConfig,
    FeedbackConfig,
    FinalEvalConfig,
    ModelConfig,
    SimulationConfig,
    TestingConfig,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_KEYS = [
    "name",
    "max_iterations",
    "seeds",
    "model",
    "designs",
    "simulation",
    "testing",
    "feedback",
    "final_eval",
]


def load_yaml(path: str) -> dict:
    """Read a YAML file relative to REPO_ROOT, applying top-level `extends:` if present."""
    data = yaml.safe_load((REPO_ROOT / path).read_text())
    if "extends" in data:
        parent = load_yaml(data.pop("extends"))
        parent.update(data)  # child keys replace parent keys
        data = parent
    return data


def find_problems(raw: dict) -> list[str]:
    """Return a list of missing keys or referenced files/folders that don't exist."""
    problems = [f"missing key: {key}" for key in REQUIRED_KEYS if key not in raw]
    if problems:
        return problems

    yaml_refs = [
        raw["model"],
        raw["designs"],
        raw["simulation"],
        *raw["testing"],
        raw["feedback"],
        raw["final_eval"],
    ]
    for path in yaml_refs:
        if not (REPO_ROOT / path).exists():
            problems.append(f"file not found: {path}")
    if problems:
        return problems

    fb = load_yaml(raw["feedback"])
    for key in ("generate_prompt", "root_cause_prompt", "fix_prompt"):
        if fb.get(key) and not (REPO_ROOT / fb[key]).exists():
            problems.append(f"prompt not found: {fb[key]}")

    for d_path in load_yaml(raw["designs"]).get("paths", []):
        if not (REPO_ROOT / d_path).exists():
            problems.append(f"design path not found: {d_path}")

    return problems


def load_experiment(path: str) -> ExperimentConfig:
    """Load an experiment file and all 6 referenced config sections into dataclasses."""
    raw = load_yaml(path)
    problems = find_problems(raw)
    if problems:
        raise ValueError("; ".join(problems))

    return ExperimentConfig(
        name=raw["name"],
        max_iterations=raw["max_iterations"],
        seeds=raw["seeds"],
        model=ModelConfig(**load_yaml(raw["model"])),
        designs=DesignsConfig(**load_yaml(raw["designs"])),
        simulation=SimulationConfig(**load_yaml(raw["simulation"])),
        testing=[TestingConfig(**load_yaml(p)) for p in raw["testing"]],
        feedback=FeedbackConfig(**load_yaml(raw["feedback"])),
        final_eval=FinalEvalConfig(**load_yaml(raw["final_eval"])),
    )


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    raw = load_yaml(sys.argv[1])
    problems = find_problems(raw)
    if problems:
        for problem in problems:
            print(f"problem: {problem}")
        return 1

    config = load_experiment(sys.argv[1])
    print(yaml.safe_dump(asdict(config), sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
