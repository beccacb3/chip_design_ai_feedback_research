"""Load experiment configs into dataclasses defined in framework/models.py.

An experiment is a YAML file in configs/experiments/. It can:

  1. Point to other files by path (model, feedback, prompts, designs).
  2. Use `extends:` to start from another experiment. Any key written in the
     child file replaces that key from the parent.

Usage (validate and print resolved config):
    python3 -m framework.config configs/experiments/baseline.yaml
"""

from dataclasses import asdict
from pathlib import Path
import sys

import yaml

from framework.models import ExperimentConfig, FeedbackConfig, ModelConfig

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_KEYS = ["name", "designs", "model", "prompts", "feedback", "max_iterations", "seeds"]


def read_yaml(path):
    """Read a YAML file given a path relative to the repo root."""
    with open(REPO_ROOT / path) as f:
        return yaml.safe_load(f)


def load_raw_experiment(path):
    """Read an experiment YAML dictionary, applying `extends:` if present."""
    config = read_yaml(path)
    if "extends" in config:
        parent = load_raw_experiment(config.pop("extends"))
        parent.update(config)  # child keys replace parent keys
        config = parent
    return config


def find_problems(raw):
    """Return a list of problems: missing keys, or paths that don't exist."""
    problems = [f"missing key: {key}" for key in REQUIRED_KEYS if key not in raw]
    if problems:
        return problems

    paths = [raw["designs"], raw["model"], *raw["feedback"], *raw["prompts"].values()]
    for path in paths:
        if not (REPO_ROOT / path).exists():
            problems.append(f"file not found: {path}")
    return problems


def load_experiment(path) -> ExperimentConfig:
    """Load an experiment file and resolve its model and feedback into dataclasses."""
    raw = load_raw_experiment(path)
    problems = find_problems(raw)
    if problems:
        raise ValueError("; ".join(problems))

    model = ModelConfig(**read_yaml(raw["model"]))
    feedback = [FeedbackConfig(**read_yaml(fb_path)) for fb_path in raw["feedback"]]

    return ExperimentConfig(
        name=raw["name"],
        designs=raw["designs"],
        model=model,
        prompts=raw["prompts"],
        feedback=feedback,
        max_iterations=raw["max_iterations"],
        seeds=raw["seeds"],
    )


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    raw = load_raw_experiment(sys.argv[1])
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
