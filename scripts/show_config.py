"""Print an experiment's final config and any problems with it.

Usage:
    python scripts/show_config.py configs/experiments/baseline.yaml
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from framework.config import find_problems, load_experiment, load_referenced_files  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    config = load_experiment(sys.argv[1])
    problems = find_problems(config)
    if problems:
        for problem in problems:
            print(f"problem: {problem}")
        return 1

    print(yaml.safe_dump(load_referenced_files(config), sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
