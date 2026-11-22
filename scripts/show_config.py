"""Print an experiment's resolved ExperimentConfig and any problems with it.

Usage:
    python scripts/show_config.py configs/experiments/baseline.yaml
"""

from dataclasses import asdict
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from framework.config import find_problems, load_experiment, load_raw_experiment  # noqa: E402


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
