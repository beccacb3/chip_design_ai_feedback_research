"""Load experiment configs.

An experiment is a YAML file in configs/experiments/. It can:

  1. Point to other files by path (model, feedback, prompts, designs).
  2. Use `extends:` to start from another experiment. Any key written in the
     child file replaces that key from the parent. Nothing is merged deeper
     than that, so a child that sets `feedback:` replaces the whole list.

All paths are relative to the repo root.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_KEYS = ["name", "designs", "model", "prompts", "feedback", "max_iterations"]


def read_yaml(path):
    """Read a YAML file given a path relative to the repo root."""
    with open(REPO_ROOT / path) as f:
        return yaml.safe_load(f)


def load_experiment(path):
    """Read an experiment file, applying `extends:` if present."""
    config = read_yaml(path)
    if "extends" in config:
        parent = load_experiment(config.pop("extends"))
        parent.update(config)  # child keys replace parent keys
        config = parent
    return config


def load_referenced_files(config):
    """Return a copy of the config with the model and feedback files read in."""
    full = dict(config)
    full["model"] = read_yaml(config["model"])
    full["feedback"] = [read_yaml(path) for path in config["feedback"]]
    return full


def find_problems(config):
    """Return a list of problems: missing keys, or paths that don't exist."""
    problems = [f"missing key: {key}" for key in REQUIRED_KEYS if key not in config]
    if problems:
        return problems

    paths = [config["designs"], config["model"], *config["feedback"], *config["prompts"].values()]
    for path in paths:
        if not (REPO_ROOT / path).exists():
            problems.append(f"file not found: {path}")
    return problems
