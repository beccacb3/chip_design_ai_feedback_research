"""Comparison report: aggregates summary.json across runs/ into a Markdown table.

Entry point for `make report`:
    python3 -m evaluation.report [runs/]
"""

import json
from pathlib import Path
import sys


def build_report(runs_root: Path) -> str:
    """Read summary.json from every run folder under runs_root and return a Markdown table."""
    summaries = [
        json.loads(p.read_text())
        for p in sorted(Path(runs_root).glob("*/*/summary.json"))
    ]
    if not summaries:
        return "No runs found in runs/."

    header = (
        "| Experiment | Model | Trials | Compile % | Golden Pass % | FPR % | "
        "Coverage % | Mutation Kill % | Audit Pass % | Avg Turns | Tokens | Cost ($) | Time (s) |\n"
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    rows = []
    for s in summaries:
        rows.append(
            f"| {s['experiment']} | {s['model']} | {s['num_trials']} | "
            f"{s['compile_pass_rate']:.0%} | {s['golden_rtl_pass_rate']:.0%} | "
            f"{s['false_positive_rate']:.0%} | {s['avg_coverage_score']:.0%} | "
            f"{s['avg_mutation_score']:.0%} | {s['assertion_audit_pass_rate']:.0%} | "
            f"{s['avg_turns']:.2f} | {s['total_tokens']} | "
            f"${s['total_cost_usd']:.4f} | {s['total_wall_time_s']:.2f} |"
        )
    return "\n".join([header, *rows])


def main():
    runs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs")
    print(build_report(runs_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
