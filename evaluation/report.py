"""Comparison report: aggregates summary.json across runs/ into a Markdown table
covering Section 4.1.1 - 4.1.7 of the Research Ideation Report.

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
        "| Experiment | Model | Trials | Golden Accept (4.1.3) | Mutation Kill (4.1.2) | "
        "Code Cov (4.1.5) | Req Group Cov (4.1.6) | Func Cov (4.1.7) | Missed vs Golden (4.1.1) | "
        "Avg Turns | LLM Calls | Tokens | Cost ($) | Sim Time (s) |\n"
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    rows = []
    for s in summaries:
        rows.append(
            f"| {s['experiment']} | {s['model']} | {s['num_trials']} | "
            f"{s['golden_rtl_acceptance_rate']:.0%} | {s['avg_mutation_score']:.0%} | "
            f"{s['avg_code_coverage']:.0%} | {s['avg_req_group_coverage']:.0%} | "
            f"{s['avg_functional_coverage']:.0%} | {s['avg_missed_scenarios_vs_golden']:.2f} | "
            f"{s['avg_turns']:.2f} | {s['total_llm_calls']} | {s['total_tokens']} | "
            f"${s['total_cost_usd']:.4f} | {s['total_sim_wall_time_s']:.2f} |"
        )
    return "\n".join([header, *rows])


def main():
    runs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs")
    print(build_report(runs_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
