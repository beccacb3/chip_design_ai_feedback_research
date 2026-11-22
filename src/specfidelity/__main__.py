"""CLI.

  python -m specfidelity resolve configs/experiments/<x>.yaml [-o key=value ...]
  python -m specfidelity plan    configs/experiments/<x>.yaml [-o key=value ...]

`resolve` prints the fully resolved config(s) -- what a run would snapshot as
resolved_config.yaml. `plan` lists the sweep variants and design count.
The runner itself is not implemented yet.
"""

from __future__ import annotations

import argparse
import sys

import yaml

from .config import ConfigError, find_repo_root, load_experiment, suite_designs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="specfidelity")
    ap.add_argument("command", choices=["resolve", "plan"])
    ap.add_argument("experiment")
    ap.add_argument("-o", "--override", action="append", default=[], metavar="KEY=VALUE")
    args = ap.parse_args(argv)

    root = find_repo_root()
    try:
        results = load_experiment(args.experiment, args.override, root)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    failed = False
    for cfg, report in results:
        label = cfg.get("variant") or cfg.get("name")
        for w in report.warnings:
            print(f"warning [{label}]: {w}", file=sys.stderr)
        for e in report.errors:
            print(f"error   [{label}]: {e}", file=sys.stderr)
        failed |= bool(report.errors)

        if args.command == "resolve":
            print(yaml.safe_dump(cfg, sort_keys=False), end="---\n")
        else:
            n = len(suite_designs(cfg["suite"], root)) if isinstance(cfg.get("suite"), dict) else 0
            print(
                f"{cfg['name']:<28} {cfg.get('variant', '-'):<40} "
                f"designs={n} seeds={len(cfg.get('seeds', [0]))}"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
